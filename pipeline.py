import asyncio
import json
import os
import re
from pathlib import Path

from tenacity import retry, stop_after_attempt, wait_exponential

from llm_from_config_anthropic import (
    UnifiedDynamicAnthropicModel,
    get_anthropic_model_from_config,
)
from llm_summarizer import (
    SummarizerAnthropicModel,
    get_anthropic_summarizer_from_config,
)


class ExtractionPipeline:
    def __init__(
        self,
        extractor_model_config_key: str,
        summarizer_model_config_key: str,
        colleagues_filepath: str,
        input_folder: str,
        output_folder: str,
        anonymized_folder: str,
        max_concurrency: int = 5,
    ):
        self._input_folder: str = input_folder
        self._output_folder: str = output_folder
        self._anonymized_folder: str = anonymized_folder
        self._colleagues_filepath: str = colleagues_filepath

        self._txt_list: list[str] = self._get_txt_files(self._input_folder)
        self._anonymization_dict: dict[str, dict[str, str]] = (
            self._build_anonymization_dict()
        )

        self._llm_extractor: UnifiedDynamicAnthropicModel = (
            get_anthropic_model_from_config(model_config_key=extractor_model_config_key)
        )
        self._llm_summarizer: SummarizerAnthropicModel = (
            get_anthropic_summarizer_from_config(
                model_config_key=summarizer_model_config_key
            )
        )

        # Create a semaphore to limit concurrent API calls
        self._semaphore = asyncio.Semaphore(max_concurrency)

    def _build_anonymization_dict(self):
        """Reads the colleagues file and builds a dictionary for anonymization."""
        people_dict = {}
        with open(self._colleagues_filepath, "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line or line == "Characters:":
                    continue
                match = re.search(r"^(.*?):\s*(.*?)\s*\(([^@]+@[^)]+)\)", line)
                if match:
                    role = match.group(1).strip()
                    name = match.group(2).strip()
                    email = match.group(3).strip()

                    email_prefix = re.sub(r"[^a-zA-Z0-9]", "", role.lower())
                    anonymized_email = f"{email_prefix}@anonymized.com"

                    people_dict[email] = {
                        "original_name": name,
                        "anonymized_role": role,
                        "anonymized_email": anonymized_email,
                    }
        return people_dict

    def _get_txt_files(self, folder_path: str) -> list[str]:
        """Returns a list of all .txt files in the specified folder."""
        folder = Path(folder_path)
        return [str(file) for file in folder.glob("*.txt")]

    def _save_to_txt_file(self, content: str, filename: str):
        """Saves the given content to a .txt file in the output folder."""
        os.makedirs(self._output_folder, exist_ok=True)
        output_filepath = os.path.join(self._output_folder, filename)
        with open(output_filepath, "w", encoding="utf-8") as file:
            file.write(content)
        print(f"Saved content to: {output_filepath}")

    def _anonymize_email_file(self, input_filepath: str) -> str:
        """Reads, anonymizes, and saves the file properly. Returns the filepath of the new file."""
        with open(input_filepath, "r", encoding="utf-8") as file:
            anonymized_text = file.read()

        exact_replacements = {}
        partial_names = set()

        for original_email, data in self._anonymization_dict.items():
            exact_replacements[original_email] = data["anonymized_email"]
            exact_replacements[data["original_name"]] = data["anonymized_role"]
            for part in data["original_name"].split():
                partial_names.add(part)

        sorted_exact_keys = sorted(exact_replacements.keys(), key=len, reverse=True)
        for key in sorted_exact_keys:
            if "@" in key:
                anonymized_text = anonymized_text.replace(key, exact_replacements[key])
            else:
                anonymized_text = re.sub(
                    rf"\b{re.escape(key)}\b",
                    exact_replacements[key],
                    anonymized_text,
                    flags=re.IGNORECASE,
                )

        sorted_partial_names = sorted(list(partial_names), key=len, reverse=True)
        for name_part in sorted_partial_names:
            anonymized_text = re.sub(
                rf"\b{re.escape(name_part)}\b",
                "[ANONYMIZED_NAME]",
                anonymized_text,
                flags=re.IGNORECASE,
            )

        os.makedirs(self._anonymized_folder, exist_ok=True)
        base_filename = os.path.basename(input_filepath)
        anon_filepath = os.path.join(self._anonymized_folder, f"Anon_{base_filename}")

        with open(anon_filepath, "w", encoding="utf-8") as file:
            file.write(anonymized_text)

        return anon_filepath

    def _format_portfolio_health_report(self, report: dict) -> str:
        """Formats the raw report data into a human-readable string."""
        data = (
            report.model_dump()
            if hasattr(report, "model_dump")
            else report.dict()
            if hasattr(report, "dict")
            else report
        )
        health_status = data.get("overall_health_status", "UNKNOWN")
        flags = data.get("extracted_flags", [])

        # Here a loop could be used to check if the flags match the main flag of the email threads,
        # because there is a possibility that multiple projects are discussed in the same email thread
        # project_name = flags[0].get('project_name', 'Unknown Project') if flags else 'Unknown Project'
        project_name = data.get("project_name", "Unknown Project")

        output = [
            "=" * 80,
            f"PROJECT: {project_name.upper()}",
            f"OVERALL HEALTH STATUS: {health_status.upper()}",
            f"Total Attention Flags Detected: {len(flags)}",
            "=" * 80 + "\n",
        ]

        for i, flag in enumerate(flags, 1):
            types = flag.get("flag_types", [flag.get("flag_type", "Unknown")])
            types_str = " | ".join(types) if isinstance(types, list) else types
            status_icon = "✅ RESOLVED" if flag.get("is_resolved") else "❌ UNRESOLVED"

            output.extend(
                [
                    f"🚩 FLAG {i}: {types_str} [{flag.get('severity', 'Unknown').upper()} SEVERITY]",
                    f"   Status:    {status_icon}",
                    f"   Date:      {flag.get('date_reported', 'Unknown')}",
                    f"   People:    Raised by {flag.get('reported_by', 'Unknown')} ➡️ Assigned to {flag.get('assigned_to', 'Unknown')}",
                    f"   Summary:   {flag.get('summary', 'No summary.')}",
                    f'   Evidence:  "{flag.get("evidence_quote", "No evidence.")}"',
                    "-" * 80,
                ]
            )
        return "\n".join(output)

    async def _process_project_file(self, anonymized_file_path: str):
        """Processes a single anonymized email file: extracts flags and formats the report."""
        os.makedirs(self._output_folder, exist_ok=True)
        base_filename = os.path.basename(anonymized_file_path).replace("Anon_", "")
        file_name = base_filename.replace(".txt", "").replace("_", " ").title()
        output_filepath = os.path.join(self._output_folder, f"Report_{base_filename}")

        print(f"⏳ Extracting Flags for: {file_name}...")

        try:
            with open(anonymized_file_path, "r", encoding="utf-8") as f:
                email_text = f.read()

            result = await self._safe_extract(email_text=email_text)
            data_dict = (
                result.model_dump()
                if hasattr(result, "model_dump")
                else result.dict()
                if hasattr(result, "dict")
                else result
            )

            print(f"\n{'=' * 20} RAW LLM JSON: {base_filename} {'=' * 20}")
            print(json.dumps(data_dict, indent=2))
            print("=" * 60 + "\n")

            formatted_text = self._format_portfolio_health_report(data_dict)

            with open(output_filepath, "w", encoding="utf-8") as f:
                f.write(formatted_text)

            print(f"✅ Extracted successfully: {output_filepath}")

            project_name = data_dict.get("project_name", "Unknown Project")
            return project_name, data_dict

        except Exception as e:
            print(f"Failed extraction on {base_filename}. Error: {str(e)}")
            return None, None

    @retry(
        wait=wait_exponential(multiplier=2, min=10, max=60), stop=stop_after_attempt(5)
    )
    async def _safe_extract(self, email_text: str):
        """Wraps the extractor LLM call in an exponential backoff retry block."""
        async with self._semaphore:
            return await self._llm_extractor.ainvoke(email_threads=email_text)

    @retry(
        wait=wait_exponential(multiplier=2, min=10, max=60), stop=stop_after_attempt(5)
    )
    async def _safe_summarize(self, formatted_result: str):
        """Wraps the summarizer LLM call in an exponential backoff retry block."""
        async with self._semaphore:
            return await self._llm_summarizer.ainvoke(aggregated_flags=formatted_result)

    async def _run_pipeline_sequential(self):
        """Runs the entire pipeline sequentially but preserves the Map-Reduce grouping logic."""

        anonymized_paths = [self._anonymize_email_file(f) for f in self._txt_list]

        results = []
        for anon_path in anonymized_paths:
            results.append(await self._process_project_file(anon_path))

        project_aggregated_flags = {}

        for project_name, data_dict in results:
            if not data_dict or not project_name:
                continue

            flags = data_dict.get("extracted_flags", [])

            if not flags or len(flags) == 0:
                continue

            proj_key = project_name.strip().upper()

            if proj_key not in project_aggregated_flags:
                project_aggregated_flags[proj_key] = []

            project_aggregated_flags[proj_key].extend(flags)

        print(
            f"\n⏳ Generating {len(project_aggregated_flags)} Project-Level Executive Summaries..."
        )

        for proj_key, combined_flags in project_aggregated_flags.items():
            combined_data_dict = {
                "project_name": proj_key,
                "overall_health_status": "AT RISK",
                "extracted_flags": combined_flags,
            }

            combined_formatted_text = self._format_portfolio_health_report(
                combined_data_dict
            )

            summary = await self._llm_summarizer.ainvoke(
                aggregated_flags=combined_formatted_text
            )

            print(f"\nExecutive Summary for {proj_key}:\n{summary}\n")

            safe_project_name = re.sub(r'[\\/*?:"<>|]', "_", proj_key)
            clean_filename = (
                f"Executive_Summary_{safe_project_name.replace(' ', '_').title()}.txt"
            )
            self._save_to_txt_file(summary, clean_filename)

    async def _run_pipeline_parallel(self):
        """Runs the pipeline in parallel: anonymize all files, then extract all, then summarize all, and finally save all."""
        # 1. Anonymize all files sequentially
        anonymized_paths = [self._anonymize_email_file(f) for f in self._txt_list]

        # 2. MAP: Extract reports in parallel
        tasks = [
            self._process_project_file(anon_path) for anon_path in anonymized_paths
        ]
        results = await asyncio.gather(*tasks)

        # 3. REDUCE: Group flags by Project Name and filter out 0-flag threads
        project_aggregated_flags = {}

        for project_name, data_dict in results:
            if not data_dict or not project_name:
                continue

            flags = data_dict.get("extracted_flags", [])

            # Skip if there are no flags
            if not flags or len(flags) == 0:
                continue

            proj_key = project_name.strip().upper()

            if proj_key not in project_aggregated_flags:
                project_aggregated_flags[proj_key] = []

            # Combine the flags from different email threads into one master list
            project_aggregated_flags[proj_key].extend(flags)

        # 4. SUMMARIZE: Run summarizer once per Project
        summary_tasks = []
        projects_to_summarize = []

        for project_name, combined_flags in project_aggregated_flags.items():
            projects_to_summarize.append(project_name)

            combined_data_dict = {
                "project_name": project_name,
                "overall_health_status": "AT RISK",  # If it has flags, it's at risk
                "extracted_flags": combined_flags,
            }
            combined_formatted_text = self._format_portfolio_health_report(
                combined_data_dict
            )

            # Send the master project text to the summarizer
            summary_tasks.append(self._safe_summarize(combined_formatted_text))

        print(
            f"\n⏳ Generating {len(projects_to_summarize)} Project-Level Executive Summaries..."
        )
        report_summaries = await asyncio.gather(*summary_tasks)

        # 5. SAVE: Write the project-level summaries to disk
        for project_name, summary in zip(projects_to_summarize, report_summaries):
            safe_project_name = re.sub(r'[\\/*?:"<>|]', "_", project_name)
            clean_filename = (
                f"Executive_Summary_{safe_project_name.replace(' ', '_').title()}.txt"
            )
            self._save_to_txt_file(summary, clean_filename)
            print(f"\nFinal Executive Summary for {project_name}:\n{summary}\n")

    async def run(self, parallel: bool = True):
        """Main method to run the pipeline. If parallel=True, it will run the parallel version; otherwise, it will run sequentially."""
        if parallel:
            await self._run_pipeline_parallel()
        else:
            await self._run_pipeline_sequential()
