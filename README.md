# RFP Evaluation Tool

A web application that evaluates RFP (Request for Proposal) responses against custom rubrics using OpenAI's GPT-4 API. The tool provides detailed scores, reasoning, and actionable fix suggestions for each metric in your rubric.

## Features

- **Interactive Web Interface**: Clean, modern UI for inputting RFP text and rubrics
- **AI-Powered Evaluation**: Uses OpenAI GPT-4 to analyze RFP responses against custom rubrics
- **Structured Output**: Provides scores (1-5), reasoning, and fix prompts for each metric
- **Summary & Recommendations**: Includes overall summary and most impactful fix suggestions

## Setup

### Prerequisites

- Python 3.8 or higher
- OpenAI API key

### Installation

1. Clone or download this repository

2. Create a virtual environment (recommended):
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up your OpenAI API key:
   - Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
   - Edit `.env` and add your OpenAI API key:
   ```
   OPENAI_API_KEY=your_actual_api_key_here
   ```

### Running the Application

1. Activate the virtual environment (if not already activated):
```bash
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Start the Flask server:
```bash
python app.py
```

3. Open your browser and navigate to:
```
http://localhost:5000
```

4. Enter your RFP response section and rubric, then click "Evaluate"

## Usage

1. **Paste RFP Response**: Enter the RFP response section you want to evaluate in the first text area
2. **Paste Rubric**: Enter your evaluation rubric in the second text area
3. **Click Evaluate**: The tool will send the inputs to OpenAI and display formatted results
4. **Review Results**: View scores, reasoning, fix prompts, summary, and most impactful fix suggestions

## Example

**RFP Response Section:**
```
Our company understands your need for scalable cloud infrastructure...
```

**Rubric:**
```
- Has the document restated and interpreted the buyer's needs in their own context?
- Structure & Organization
- Technical accuracy
- Value proposition clarity
```

The tool will generate a table with scores, reasoning, and fix prompts for each metric, plus an overall summary.

## Project Structure

```
eval-tool/
├── app.py                 # Flask application
├── requirements.txt       # Python dependencies
├── .env.example          # Example environment file
├── .gitignore            # Git ignore rules
├── templates/
│   └── index.html        # Main UI page
├── static/
│   └── css/
│       └── style.css     # Styling
└── README.md             # This file
```

## Phase 2 (Future)

- Support for multiple RFP sections
- Different rubrics per section
- Batch evaluation interface
- Export results functionality

## Notes

- Make sure your OpenAI API key has sufficient credits
- The tool uses GPT-4 by default (can be changed in `app.py`)
- Results are displayed in a formatted table matching the example output format

## License

This project is provided as-is for evaluation purposes.

