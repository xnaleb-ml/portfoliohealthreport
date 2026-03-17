from typing import (
    Any,
    Literal,
    Optional,
    Type,
    TypeVar,
)

from langchain_anthropic import ChatAnthropic
from langchain_core.callbacks.manager import (
    AsyncCallbackManagerForToolRun,
    CallbackManagerForToolRun,
)
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, ValidationError, create_model

from config import load_yaml_config
from settings import get_settings

SchemaT = TypeVar("SchemaT", bound=BaseModel)


def eval_types(fields_config: dict) -> dict:
    field_definitions = {}

    type_map = {
        "str": str,
        "bool": bool,
        "int": int,
        "float": float,
        "dict": dict,
        "list": list,
        "list[str]": list[str],
        "list[dict]": list[dict],
    }

    for field_name, field_config in fields_config.items():
        field_type_str = field_config.get("type", "str")
        description = field_config.get("description", f"The {field_name} field.")
        values = field_config.get("values")

        if field_type_str == "str" and values:
            field_type = Literal[tuple(values)]
        else:
            field_type = type_map.get(field_type_str)
            if field_type is None:
                print(
                    f"WARNING: Unknown type '{field_type_str}' requested for '{field_name}'. "
                    f"Defaulting to str for safety."
                )
                field_type = str

        is_optional = field_config.get("optional", False)

        if is_optional:
            field_obj = Field(default=None, description=description)
            field_definitions[field_name] = (Optional[field_type], field_obj)
        else:
            field_obj = Field(description=description)
            field_definitions[field_name] = (field_type, field_obj)

    return field_definitions


def create_classifier_schema(config: dict) -> Type[BaseModel]:
    """
    Dynamically create a Pydantic model for the classifier based on the configuration.

    Args:
        config: Dictionary containing field definitions from tool_definition

    Returns:
        A dynamically created Pydantic model class
    """
    fields_config = config.get("tool_definition", {}).get("fields", {})

    if not fields_config:
        raise ValueError(
            "No fields found in tool_definition. Check your config structure."
        )

    field_definitions = eval_types(fields_config=fields_config)

    if not field_definitions:
        raise ValueError(
            "No field definitions were created. Check your config structure."
        )

    # Create the schema with a meaningful name
    schema_name = config.get("schema_name", "ClassifierSchema")
    schema_docstring = "Schema for classification using tool-calling."

    # Create model with docstring
    model = create_model(schema_name, __doc__=schema_docstring, **field_definitions)

    return model


def create_output_validation_schema(config: dict) -> Type[BaseModel]:
    """
    Create a Pydantic schema for validating the tool's output.
    This is similar to the input schema but ensures all fields are properly validated.

    Args:
        config: Dictionary containing field definitions from tool_definition

    Returns:
        A Pydantic model class for output validation
    """
    fields_config = config.get("tool_definition", {}).get("fields", {})

    if not fields_config:
        raise ValueError("No fields found in tool_definition for validation schema.")

    field_definitions = eval_types(fields_config=fields_config)

    if not field_definitions:
        raise ValueError(
            "No field definitions were created. Check your config structure."
        )

    # Create the validation schema
    validation_schema_name = config.get(
        "validation_schema_name", "ClassifierOutputSchema"
    )
    validation_schema_docstring = "Schema for validating classifier tool output."

    # Create the base model
    ValidationModel = create_model(
        validation_schema_name, __doc__=validation_schema_docstring, **field_definitions
    )

    return ValidationModel


def create_classifier_tool(
    config: dict, schema_class: Type[BaseModel]
) -> Type[BaseTool]:
    """
    Dynamically create a Classifier Tool class based on the configuration.

    Args:
        config: Dictionary containing the full classifier configuration
        schema_class: The Pydantic schema class to use for this tool

    Returns:
        A dynamically created Tool class
    """
    tool_name = config.get("tool_name", "Classifier_tool")

    # Get the tool description
    tool_description = config.get("tool_description", "")

    # Extract field names from schema for the _run and _arun methods
    field_names = list(config.get("tool_definition", {}).get("fields", {}).keys())

    class DynamicClassifierTool(BaseTool):
        """Dynamically created classifier tool."""

        name: str = tool_name
        description: str = tool_description
        args_schema: Type[BaseModel] = schema_class
        return_direct: bool = config.get("return_direct", True)

        def _run(
            self, run_manager: Optional[CallbackManagerForToolRun] = None, **kwargs
        ) -> dict[str, Any]:
            """Use the tool."""
            # Return only the fields that were defined in the schema
            result = {k: v for k, v in kwargs.items() if k in field_names}
            return result

        async def _arun(
            self, run_manager: Optional[AsyncCallbackManagerForToolRun] = None, **kwargs
        ) -> dict[str, Any]:
            """Use the tool asynchronously."""
            # Return only the fields that were defined in the schema
            result = {k: v for k, v in kwargs.items() if k in field_names}
            return result

    return DynamicClassifierTool


def create_classifier_from_config(
    config: dict,
) -> tuple[Type[BaseModel], Type[BaseTool]]:
    """
    Create both schema and tool from a configuration dictionary.

    Args:
        config: Dictionary containing the classifier configuration

    Returns:
        Tuple of (schema_class, tool_class)
    """
    schema_class = create_classifier_schema(config)
    tool_class = create_classifier_tool(config, schema_class)
    return schema_class, tool_class


class UnifiedDynamicAnthropicModel:
    """
    A unified class for calling Anthropic Claude LLMs with forced tool-calling.
    """

    def __init__(
        self,
        model_name: str,
        api_key: str,
        temperature: float = 0.0,
        max_tokens: int = 4000,
        tool: type = None,
        output_validator_schema: BaseModel = None,
        prompt_template: str = None,
        system_prompt: str = None,
    ):
        self._model_name = model_name
        self._system_prompt = system_prompt
        llm = ChatAnthropic(
            model=model_name,
            api_key=api_key,
            temperature=temperature,
            max_tokens_to_sample=max_tokens,
        )

        tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.args_schema.model_json_schema(),
            }
        ]
        self._tools = tools

        self._llm = llm.bind_tools(tools=tools, tool_choice=tool.name)
        self._validator = output_validator_schema

        self._prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", prompt_template),
            ]
        )

        self.expected_inputs = self._prompt.input_variables
        self._conversation = self._prompt | self._llm

    async def ainvoke(self, **kwargs):
        try:
            missing_vars = [var for var in self.expected_inputs if var not in kwargs]
            if missing_vars:
                raise ValueError(
                    f"Missing arguments for prompt template: {missing_vars}"
                )

            result = await self._conversation.ainvoke(kwargs)

            if not result.tool_calls or len(result.tool_calls) == 0:
                print("No tool calls returned from Claude.")
                raise RuntimeError("Claude failed to return the structured tool call.")

            validated_result = self._validator.model_validate(
                result.tool_calls[0]["args"]
            )
            return validated_result
        except (KeyError, IndexError, TypeError, ValidationError) as e:
            print(f"Error in tool execution: {e}")
            raise RuntimeError("Classifier tool execution failed.") from e


def get_anthropic_model_from_config(
    model_config_key: str,
) -> UnifiedDynamicAnthropicModel:
    CONFIG = load_yaml_config()
    settings = get_settings()
    _, model_tool = create_classifier_from_config(config=CONFIG.get(model_config_key))
    validator_schema = create_output_validation_schema(
        config=CONFIG.get(model_config_key)
    )

    system_prompt = CONFIG.get(model_config_key).get("prompt", "")

    kwargs = {
        "api_key": settings.llm.anthropic_api_key,
        "model_name": settings.llm.llm_model,
        "temperature": settings.llm.default_llm_temperature,
        "max_tokens": settings.llm.max_tokens_to_generate,
        "tool": model_tool(),
        "output_validator_schema": validator_schema,
        "prompt_template": CONFIG.get(model_config_key).get("prompt_template"),
        "system_prompt": system_prompt,
    }

    return UnifiedDynamicAnthropicModel(**kwargs)
