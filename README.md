# Portfolio Health Report Engine

This repository contains the Proof of Concept (PoC) for an automated, AI-driven project health analysis tool, designed to extract critical attention flags from anonymized project communications, and to create a natural language summary per project.

## Repository Structure
```
.
├── Data folder                    # Contains the unzipped input email files
├── Output folder                  # Contains the results from running the pipeline
├── Blueprint.md                   # Detailed architecture & production scaling strategy
├── Colleagues.txt                 # The provided txt file containing names and emails
├── config.py                      # Helper to load the config.yaml
├── config.yaml                    # System prompts and dynamic schema definitions
├── llm_from_config_anthropic.py   # Dynamic schema generation & Extractor tool calling
├── llm_summarizer.py              # Prose generation for the final Executive Summaries
├── pipeline.py                    # Core orchestration logic
├── README.md                      # Project overview and setup instructions
├── requirements.txt               # Python dependencies
├── run_pipeline.ipynb             # Interactive execution notebook
├── schemas.py                     # Pydantic model for the Attention Flags
└── settings.py                    # Environment variable management (Pydantic Settings)

```

## AI Model Justification

For this pipeline, I chose to use **Anthropic's Claude 4.6 Sonnet** as the core analytical engine for both the Extraction and Summarization steps. 

**Why Claude 4.6 Sonnet?**
1. **Superior Structured Output (Tool Calling):** The extraction step relies heavily on strict Pydantic schemas to enforce fields. Claude 4.6 Sonnet is currently industry-leading at adhering to complex, nested JSON schemas without hallucinating keys.
2. **Nuanced Instruction Following:** The prompt relies on complex negative constraints (e.g., "Permission to be Healthy", "Ignore office banter"). Sonnet excels at understanding nuanced boundary conditions compared to smaller models.
3. **Separation of Concerns:** By using the same highly capable model for both the Extraction and Summarization phases, the PoC establishes a strong baseline of maximum accuracy. In a future production iteration, the steps could be downgraded to a faster/cheaper model (like Claude Haiku) to optimize costs.
4. **Quick prototyping**: Since the Sonnet model is very capable, it is perfect for creating PoC showcases, then later optimize.

## How to Run the Code
The code uses a venv with python 3.13.1.
**1. Clone the repository**
```bash
git clone https://github.com/xnaleb-ml/portfoliohealthreport.git
cd portfoliohealthreport
```
**2. Create and activate a Virtual Environment**
```bash
# Create the virtual environment
python -m venv venv

# Activate on Windows:
venv\Scripts\activate

# Activate on macOS/Linux:
source venv/bin/activate
```
**3. Install dependencies**
```bash
pip install -r requirements.txt
```
**4. Configure Environment Variables and run pipeline**
The `run_pipeline.ipynb` notebook demonstrates the usage. A `CLAUDE_API_KEY` is required and has to be given in the first code block:
```python
import os
from pathlib import Path

from pipeline import ExtractionPipeline

# Set up environment variables and paths
BASE_DIR = Path.cwd()
# A CLAUDE_API_KEY is required to run the pipeline, set it as an environment variable
CLAUDE_API_KEY = ""

os.environ["ANTHROPIC_API_KEY"] = CLAUDE_API_KEY
os.environ["LLM_MODEL"] = "claude-sonnet-4-6"
os.environ["DEFAULT_LLM_TEMPERATURE"] = "0.0"
os.environ["MAX_TOKENS_TO_GENERATE"] = "10000"

```
The following blocks guide through the execution.
