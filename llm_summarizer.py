from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate

from config import load_yaml_config
from settings import get_settings


class SummarizerAnthropicModel:
    """
    A class for calling Anthropic Claude LLMs for standard text generation.
    No tool-calling or structured data extraction is used here.
    """

    def __init__(
        self,
        model_name: str,
        api_key: str,
        temperature: float = 0.0,
        max_tokens: int = 4000,
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

        self._prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", prompt_template),
            ]
        )

        self.expected_inputs = self._prompt.input_variables
        self._conversation = self._prompt | llm

    async def ainvoke(self, **kwargs) -> str:
        """
        Executes the prompt and returns the raw string content.
        """
        try:
            # Validate that all required template variables were passed
            missing_vars = [var for var in self.expected_inputs if var not in kwargs]
            if missing_vars:
                raise ValueError(
                    f"Missing arguments for prompt template: {missing_vars}"
                )

            result = await self._conversation.ainvoke(kwargs)

            return result.content

        except Exception as e:
            print(f"Error in summarizer execution: {e}")
            raise RuntimeError("Summarizer execution failed.") from e


def get_anthropic_summarizer_from_config(
    model_config_key: str,
) -> SummarizerAnthropicModel:
    """
    Builds the summarizer model based on the YAML configuration.
    """
    CONFIG = load_yaml_config()
    settings = get_settings()

    config_data = CONFIG.get(model_config_key)
    if not config_data:
        raise ValueError(f"Configuration key '{model_config_key}' not found in yaml.")

    kwargs = {
        "api_key": settings.llm.anthropic_api_key,
        "model_name": settings.llm.llm_model,
        "temperature": settings.llm.default_llm_temperature,
        "max_tokens": settings.llm.max_tokens_to_generate,
        "prompt_template": config_data.get("prompt_template", ""),
        "system_prompt": config_data.get("prompt", ""),
    }

    return SummarizerAnthropicModel(**kwargs)
