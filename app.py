import os
import logging
import sys
import re
import json
import tempfile
import pdfplumber
from flask import Flask, render_template, request, jsonify, send_file
from openai import OpenAI
from openai import AuthenticationError, RateLimitError, APIError
from dotenv import load_dotenv
from datetime import datetime
from werkzeug.utils import secure_filename
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from io import BytesIO

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if os.getenv('FLASK_DEBUG', 'False').lower() == 'true' else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('app.log')
    ]
)

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
# Use system temp directory for cross-platform compatibility
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()  # Temporary folder for uploads

# Initialize OpenAI client (lazy initialization)
client = None

def get_openai_client():
    """Get or initialize OpenAI client"""
    global client
    if client is None:
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.error("OPENAI_API_KEY environment variable is not set")
            raise ValueError("OPENAI_API_KEY environment variable is not set. Please set it in your environment variables.")
        logger.info("Initializing OpenAI client")
        client = OpenAI(api_key=api_key)
        logger.info("OpenAI client initialized successfully")
    return client


@app.route('/')
def index():
    """Render the main page"""
    logger.info("Index page requested")
    return render_template('index.html')


def extract_sections_from_pdf(pdf_path):
    """Extract sections from PDF using pdfplumber"""
    sections = []
    current_section_title = None
    current_content = []
    section_index = 1
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    full_text += page_text + "\n"
        
        # Split text into lines for analysis
        lines = full_text.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                i += 1
                continue
            
            # Only treat ALL CAPS lines as section headings
            # Requirements:
            # 1. Must be all uppercase
            # 2. Must have at least 5 characters (to avoid false positives)
            # 3. Must contain letters (not just numbers/symbols)
            # 4. Ignore mixed-case headings (they are sub-sections, not main sections)
            is_heading = False
            
            if (line.isupper() and 
                len(line) >= 5 and 
                any(c.isalpha() for c in line) and 
                not line.isdigit()):
                # This is an ALL CAPS line - treat it as a section heading
                # All all-caps lines are sections, regardless of what follows
                is_heading = True
            
            # If it's a heading and we have a previous section, save it
            if is_heading and current_section_title is not None:
                content = '\n'.join(current_content).strip()
                if content:  # Only add if there's content
                    sections.append({
                        'index': str(section_index - 1),
                        'title': current_section_title,
                        'content': content
                    })
                current_content = []
            
            if is_heading:
                # Start new section
                current_section_title = line
                section_index += 1
            elif current_section_title is not None:
                # Add to current section content
                current_content.append(line)
            
            i += 1
        
        # Add the last section
        if current_section_title is not None:
            content = '\n'.join(current_content).strip()
            if content:
                sections.append({
                    'index': str(section_index - 1),
                    'title': current_section_title,
                    'content': content
                })
        
        # If no sections were found, treat entire document as one section
        if not sections:
            sections.append({
                'index': '1',
                'title': 'Document',
                'content': full_text.strip()
            })
        
        # Re-index sections starting from 1
        for idx, section in enumerate(sections, 1):
            section['index'] = str(idx)
        
        return sections
    
    except Exception as e:
        logger.error(f"Error extracting sections from PDF: {str(e)}", exc_info=True)
        raise


@app.route('/parse-pdf', methods=['POST'])
def parse_pdf():
    """Parse uploaded PDF and extract sections"""
    logger.info("Parse PDF endpoint called")
    
    try:
        if 'file' not in request.files:
            logger.warning("No file in request")
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            logger.warning("Empty filename")
            return jsonify({'error': 'No file selected'}), 400
        
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            logger.warning(f"Invalid file type: {file.filename}")
            return jsonify({'error': 'File must be a PDF'}), 400
        
        # Save uploaded file temporarily
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        logger.info(f"PDF saved to {filepath}, extracting sections...")
        
        # Extract sections
        sections = extract_sections_from_pdf(filepath)
        
        # Clean up temporary file
        try:
            os.remove(filepath)
        except Exception as e:
            logger.warning(f"Could not remove temporary file {filepath}: {str(e)}")
        
        logger.info(f"Extracted {len(sections)} sections from PDF")
        
        return jsonify({
            'success': True,
            'sections': sections
        })
    
    except Exception as e:
        logger.error(f"Error parsing PDF: {str(e)}", exc_info=True)
        return jsonify({
            'error': f'Error parsing PDF: {str(e)}'
        }), 500


def match_sections_with_openai(pdf_sections, rubric_sections):
    """Use OpenAI to intelligently match rubric sections to PDF sections"""
    logger.info("Using OpenAI to match sections")
    
    # Format PDF sections for the prompt
    pdf_sections_list = []
    for section in pdf_sections:
        pdf_sections_list.append({
            'index': section.get('index', ''),
            'title': section.get('title', ''),
            'content_preview': section.get('content', '')[:500]  # Include preview of content for context
        })
    
    # Format rubric sections for the prompt
    rubric_sections_list = []
    for section in rubric_sections:
        content = section.get('content', '')
        # Include full content if short, otherwise truncate intelligently
        if len(content) > 3000:
            # Try to truncate at a sentence boundary
            truncated = content[:3000]
            last_period = truncated.rfind('.')
            if last_period > 2500:  # Only truncate at period if it's not too early
                content = truncated[:last_period + 1] + "..."
            else:
                content = truncated + "..."
        
        rubric_sections_list.append({
            'title': section.get('title', ''),
            'content': content
        })
    
    # Create the prompt
    prompt = f"""You are helping to map rubric sections to PDF response sections for an RFP evaluation tool.

**PDF Response Sections (these need rubrics assigned):**
{json.dumps(pdf_sections_list, indent=2)}

**Available Rubric Sections (these contain evaluation criteria):**
{json.dumps(rubric_sections_list, indent=2)}

Your task is to match each PDF response section to the most appropriate rubric section based on:
1. Semantic similarity of section titles
2. Topic alignment and content relevance
3. Whether the rubric's evaluation criteria apply to that PDF section

Important rules:
- A rubric section can be matched to multiple PDF sections if it's relevant to all of them
- A PDF section can have no match if no rubric is appropriate (omit it from mappings)
- Only create mappings where you have at least "medium" confidence
- Consider the actual content, not just titles - use the content previews to understand context

Return your response as a JSON object with this exact format:
{{
  "mappings": [
    {{
      "pdf_section_index": "1",
      "pdf_section_title": "SECTION TITLE",
      "matched_rubric_title": "RUBRIC TITLE",
      "confidence": "high|medium|low",
      "reasoning": "Brief explanation of why this match was made"
    }}
  ]
}}

Return ONLY the JSON object, no additional text, markdown, or explanation before or after."""

    try:
        openai_client = get_openai_client()
        logger.info("Calling OpenAI API for section matching...")
        
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert at matching document sections. You must respond with valid JSON only, no additional text."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.3
        )
        
        result_text = response.choices[0].message.content
        logger.debug(f"OpenAI response: {result_text}")
        
        # Parse the JSON response
        result = json.loads(result_text)
        mappings = result.get('mappings', [])
        
        # Convert to the expected format
        matches = {}
        for mapping in mappings:
            pdf_index = mapping.get('pdf_section_index')
            rubric_title = mapping.get('matched_rubric_title', '').strip()
            
            # Find the full rubric content - use fuzzy matching for title
            matched_rubric = None
            best_match_score = 0
            
            # Normalize for comparison
            rubric_title_normalized = re.sub(r'\s+', ' ', rubric_title.upper().strip())
            
            for rubric_section in rubric_sections:
                section_title = rubric_section.get('title', '').strip()
                section_title_normalized = re.sub(r'\s+', ' ', section_title.upper().strip())
                
                # Exact match
                if section_title_normalized == rubric_title_normalized:
                    matched_rubric = rubric_section
                    break
                # Check if one contains the other (for slight variations)
                elif rubric_title_normalized in section_title_normalized or section_title_normalized in rubric_title_normalized:
                    # Prefer longer match
                    if len(section_title_normalized) > best_match_score:
                        matched_rubric = rubric_section
                        best_match_score = len(section_title_normalized)
            
            if matched_rubric and pdf_index:
                matches[pdf_index] = {
                    'rubric_title': matched_rubric.get('title', ''),
                    'rubric_content': matched_rubric.get('content', ''),
                    'match_score': 0.9 if mapping.get('confidence') == 'high' else 0.7 if mapping.get('confidence') == 'medium' else 0.5,
                    'reasoning': mapping.get('reasoning', '')
                }
        
        logger.info(f"OpenAI matched {len(matches)} sections")
        return matches
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse OpenAI JSON response: {str(e)}")
        logger.error(f"Response was: {result_text}")
        raise ValueError("OpenAI returned invalid JSON. Please try again.")
    except AuthenticationError as e:
        logger.error(f"OpenAI authentication error: {str(e)}")
        raise ValueError("OpenAI API authentication failed. Please check your API key.")
    except RateLimitError as e:
        logger.warning(f"OpenAI rate limit error: {str(e)}")
        raise ValueError("OpenAI API rate limit exceeded. Please try again in a moment.")
    except APIError as e:
        error_msg = str(e)
        logger.error(f"OpenAI API error: {error_msg}")
        if "insufficient_quota" in error_msg.lower() or "quota" in error_msg.lower():
            raise ValueError("OpenAI API quota exceeded. Please check your account billing.")
        else:
            raise ValueError(f"OpenAI API error: {error_msg}")
    except Exception as e:
        logger.error(f"Error in OpenAI matching: {str(e)}", exc_info=True)
        raise ValueError(f"Error matching sections: {str(e)}")


@app.route('/map-rubric-pdf', methods=['POST'])
def map_rubric_pdf():
    """Parse rubric PDF and match sections to existing PDF sections"""
    logger.info("Map rubric PDF endpoint called")
    
    try:
        if 'rubric_file' not in request.files:
            logger.warning("No rubric file in request")
            return jsonify({'error': 'No rubric file provided'}), 400
        
        rubric_file = request.files['rubric_file']
        
        if rubric_file.filename == '':
            logger.warning("Empty rubric filename")
            return jsonify({'error': 'No rubric file selected'}), 400
        
        # Validate file type
        if not rubric_file.filename.lower().endswith('.pdf'):
            logger.warning(f"Invalid rubric file type: {rubric_file.filename}")
            return jsonify({'error': 'Rubric file must be a PDF'}), 400
        
        # Get PDF sections from request
        pdf_sections_data = request.form.get('pdf_sections')
        if not pdf_sections_data:
            logger.warning("No PDF sections provided")
            return jsonify({'error': 'PDF sections are required'}), 400
        
        try:
            pdf_sections = json.loads(pdf_sections_data)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in PDF sections")
            return jsonify({'error': 'Invalid PDF sections data'}), 400
        
        # Save rubric file temporarily
        filename = secure_filename(rubric_file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        rubric_file.save(filepath)
        
        logger.info(f"Rubric PDF saved to {filepath}, extracting sections...")
        
        # Extract sections from rubric PDF
        rubric_sections = extract_sections_from_pdf(filepath)
        
        # Clean up temporary file
        try:
            os.remove(filepath)
        except Exception as e:
            logger.warning(f"Could not remove temporary file {filepath}: {str(e)}")
        
        logger.info(f"Extracted {len(rubric_sections)} sections from rubric PDF")
        
        # Match rubric sections to PDF sections using OpenAI
        matches = match_sections_with_openai(pdf_sections, rubric_sections)
        
        logger.info(f"Matched {len(matches)} sections using OpenAI")
        
        return jsonify({
            'success': True,
            'matches': matches,
            'rubric_sections': rubric_sections
        })
    
    except Exception as e:
        logger.error(f"Error mapping rubric PDF: {str(e)}", exc_info=True)
        return jsonify({
            'error': f'Error mapping rubric PDF: {str(e)}'
        }), 500


def is_markdown_table(text):
    """Check if the response contains a markdown table format"""
    if not text:
        return False
    
    lines = text.split('\n')
    table_row_count = 0
    
    for line in lines:
        stripped = line.strip()
        # Check if line is a markdown table row (starts and ends with |)
        if stripped.startswith('|') and stripped.endswith('|') and len(stripped) > 2:
            table_row_count += 1
        # Check if line is a table separator (contains dashes/colons between pipes)
        elif stripped.startswith('|') and stripped.endswith('|') and ('-' in stripped or ':' in stripped):
            table_row_count += 1
    
    # Require at least 2 table rows (header + at least one data row or separator)
    return table_row_count >= 2


def evaluate_single_section(rfp_text, rubric_text, retry_count=0):
    """Helper function to evaluate a single section"""
    logger.debug(f"Evaluating section - RFP text length: {len(rfp_text)}, Rubric length: {len(rubric_text)}, retry: {retry_count}")
    
    # Construct the prompt with explicit markdown table format example
    if retry_count == 0:
        prompt = f"""Evaluate the following RFP response section using the rubric below.

---

**RFP Response Section:**

```
{rfp_text}
```

**Rubric:**

{rubric_text}
---

For each metric, give:

* **Score (1–5)**
* **Reasoning**
* **Fix Prompt if score < 4** (a short instruction that could be used to revise the section toward a perfect score)

**CRITICAL: You MUST format your response as a markdown table with exactly these columns: Metric, Score, Reasoning, Fix Prompt.**

Example format:
| Metric | Score | Reasoning | Fix Prompt |
|--------|-------|-----------|------------|
| Challenge Definition & Measurable Outcomes | 2 | No buyer-specific challenge is stated... | Open with a buyer-specific problem statement... |
| Structure & Organization | 3 | The flow is logical, but... | Add clear subheadings... |

Your response must start with a table header row using pipes (|) and contain at least one data row. Do not include any text before or after the table."""
    else:
        # Stronger prompt for retry
        prompt = f"""You previously provided an evaluation, but it was not in the required markdown table format. 

**RFP Response Section:**

```
{rfp_text}
```

**Rubric:**

{rubric_text}
---

**REQUIRED FORMAT - You MUST use this exact markdown table structure:**

| Metric | Score | Reasoning | Fix Prompt |
|--------|-------|-----------|------------|
| [Metric name] | [1-5] | [Your reasoning] | [Fix prompt if score < 4] |
| [Next metric] | [1-5] | [Your reasoning] | [Fix prompt if score < 4] |

**IMPORTANT:**
- Start immediately with the table header row (| Metric | Score | Reasoning | Fix Prompt |)
- Include a separator row (|--------|-------|-----------|------------|)
- Each metric must be on its own row
- Use pipes (|) to separate columns
- Do NOT include any text before the table
- Do NOT include any text after the table
- Ensure every row starts and ends with a pipe character (|)

Provide your evaluation NOW in the required markdown table format."""
    
    logger.debug(f"Prompt constructed, length: {len(prompt)}")
    logger.info("Calling OpenAI API...")
    
    try:
        # Call OpenAI API
        start_time = datetime.now()
        openai_client = get_openai_client()
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert RFP evaluator. You MUST always format your responses as markdown tables with columns: Metric, Score, Reasoning, Fix Prompt. Never provide plain text or other formats - only markdown tables."},
                {"role": "user", "content": prompt}
            ]
        )
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.info(f"OpenAI API call completed in {duration:.2f} seconds")
        
        # Extract the response text
        result = response.choices[0].message.content
        logger.debug(f"Response received, length: {len(result)}")
        
        # Validate table format
        if not is_markdown_table(result):
            logger.warning("Response is not in markdown table format")
            if retry_count < 1:  # Retry once with stronger prompt
                logger.info("Retrying with stronger table format requirement")
                return evaluate_single_section(rfp_text, rubric_text, retry_count + 1)
            else:
                logger.warning("Retry limit reached, returning response as-is")
                # Try to extract table from response if it exists but wasn't detected
                lines = result.split('\n')
                table_lines = [line for line in lines if line.strip().startswith('|') and line.strip().endswith('|')]
                if len(table_lines) >= 2:
                    # Found some table rows, return just those
                    return '\n'.join(table_lines)
        
        return result
    except Exception as e:
        logger.error(f"Error in OpenAI API call: {str(e)}", exc_info=True)
        raise


@app.route('/evaluate', methods=['POST'])
def evaluate():
    """Evaluate RFP response sections against rubrics"""
    logger.info("Evaluate endpoint called")
    logger.debug(f"Request method: {request.method}, Content-Type: {request.content_type}")
    
    try:
        data = request.get_json()
        logger.debug(f"Received data: {data}")
        
        if not data:
            logger.warning("No data provided in request")
            return jsonify({'error': 'No data provided'}), 400
        
        # Support both old format (single section) and new format (multiple sections)
        sections = data.get('sections', [])
        logger.debug(f"Found {len(sections)} sections in request")
        
        # If sections array is empty, check for old format
        if not sections:
            logger.debug("No sections array found, checking for old format")
            rfp_text = data.get('rfp_text', '').strip()
            rubric_text = data.get('rubric', '').strip()
            if rfp_text and rubric_text:
                logger.debug("Old format detected, converting to sections array")
                sections = [{'rfp_text': rfp_text, 'rubric': rubric_text}]
        
        if not sections:
            logger.warning("No sections provided in request")
            return jsonify({'error': 'No sections provided'}), 400
        
        logger.info(f"Processing {len(sections)} section(s)")
        
        # Validate all sections
        for i, section in enumerate(sections):
            rfp_text = section.get('rfp_text', '').strip()
            rubric_text = section.get('rubric', '').strip()
            
            logger.debug(f"Validating section {i + 1}: RFP length={len(rfp_text)}, Rubric length={len(rubric_text)}")
            
            if not rfp_text:
                logger.warning(f"Section {i + 1} missing RFP text")
                return jsonify({'error': f'RFP text is required for section {i + 1}'}), 400
            
            if not rubric_text:
                logger.warning(f"Section {i + 1} missing rubric")
                return jsonify({'error': f'Rubric is required for section {i + 1}'}), 400
        
        # Process sections sequentially
        results = []
        for i, section in enumerate(sections):
            logger.info(f"Processing section {i + 1} of {len(sections)}")
            rfp_text = section.get('rfp_text', '').strip()
            rubric_text = section.get('rubric', '').strip()
            
            try:
                evaluation_result = evaluate_single_section(rfp_text, rubric_text)
                logger.info(f"Section {i + 1} evaluated successfully")
                # Include section index from request if provided
                section_idx = section.get('section_index', i)
                results.append({
                    'section_index': section_idx,
                    'success': True,
                    'result': evaluation_result
                })
            except AuthenticationError as e:
                logger.error(f"Section {i + 1}: Authentication error - {str(e)}")
                section_idx = section.get('section_index', i)
                results.append({
                    'section_index': section_idx,
                    'success': False,
                    'error': 'OpenAI API authentication failed. Please check that your OPENAI_API_KEY environment variable is correct and valid. Make sure there are no extra spaces or quotes around the key.'
                })
            except RateLimitError as e:
                logger.warning(f"Section {i + 1}: Rate limit error - {str(e)}")
                section_idx = section.get('section_index', i)
                results.append({
                    'section_index': section_idx,
                    'success': False,
                    'error': 'OpenAI API rate limit exceeded. Please try again in a moment.'
                })
            except APIError as api_error:
                error_msg = str(api_error)
                logger.error(f"Section {i + 1}: API error - {error_msg}")
                section_idx = section.get('section_index', i)
                if "insufficient_quota" in error_msg.lower() or "quota" in error_msg.lower():
                    results.append({
                        'section_index': section_idx,
                        'success': False,
                        'error': 'OpenAI API quota exceeded. Please check your OpenAI account billing and usage limits.'
                    })
                else:
                    results.append({
                        'section_index': section_idx,
                        'success': False,
                        'error': f'OpenAI API error: {error_msg}'
                    })
            except Exception as api_error:
                error_msg = str(api_error)
                logger.error(f"Section {i + 1}: Unexpected error - {error_msg}", exc_info=True)
                section_idx = section.get('section_index', i)
                # Fallback for other error types
                if "401" in error_msg or "authentication" in error_msg.lower() or "invalid_api_key" in error_msg.lower() or "access denied" in error_msg.lower():
                    results.append({
                        'section_index': section_idx,
                        'success': False,
                        'error': 'OpenAI API authentication failed. Please check that your OPENAI_API_KEY environment variable is correct and valid. Make sure there are no extra spaces or quotes around the key.'
                    })
                else:
                    results.append({
                        'section_index': section_idx,
                        'success': False,
                        'error': f'OpenAI API error: {error_msg}'
                    })
        
        logger.info(f"Evaluation complete. Processed {len(results)} result(s)")
        logger.debug(f"Results: {[r.get('success', False) for r in results]}")
        
        return jsonify({
            'success': True,
            'results': results
        })
    
    except Exception as e:
        logger.error(f"Unexpected error in evaluate endpoint: {str(e)}", exc_info=True)
        return jsonify({
            'error': f'An error occurred: {str(e)}'
        }), 500


def parse_markdown_table(table_text):
    """Parse markdown table text into structured data"""
    lines = [line.strip() for line in table_text.split('\n') if line.strip()]
    if not lines:
        return []
    
    # Find header row
    header_row = None
    separator_idx = None
    for i, line in enumerate(lines):
        if line.startswith('|') and line.endswith('|'):
            cells = [cell.strip() for cell in line.split('|')[1:-1]]
            # Check if it's a separator row
            if all(cell.replace('-', '').replace(':', '').strip() == '' for cell in cells):
                separator_idx = i
                if i > 0:
                    header_row = [cell.strip() for cell in lines[i-1].split('|')[1:-1]]
                break
            elif header_row is None:
                header_row = cells
    
    if not header_row:
        return []
    
    # Parse data rows
    data_rows = []
    start_idx = separator_idx + 1 if separator_idx else 1
    
    for line in lines[start_idx:]:
        if line.startswith('|') and line.endswith('|'):
            cells = [cell.strip() for cell in line.split('|')[1:-1]]
            if cells and any(cell for cell in cells):  # Skip empty rows
                data_rows.append(cells)
    
    return {
        'headers': header_row,
        'rows': data_rows
    }


def generate_pdf_report(sections_data, evaluation_results):
    """Generate a PDF report from sections and evaluation results"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, 
                           rightMargin=72, leftMargin=72,
                           topMargin=72, bottomMargin=72)
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Define styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#667eea'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#764ba2'),
        spaceAfter=12,
        spaceBefore=20
    )
    
    section_heading_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#667eea'),
        spaceAfter=10,
        spaceBefore=15
    )
    
    # Title
    title = Paragraph("RFP Evaluation Report", title_style)
    elements.append(title)
    elements.append(Spacer(1, 0.2*inch))
    
    # Report metadata
    report_date = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    metadata = Paragraph(f"<b>Generated:</b> {report_date}", styles['Normal'])
    elements.append(metadata)
    elements.append(Spacer(1, 0.3*inch))
    
    # Summary
    total_sections = len(sections_data)
    successful_evaluations = sum(1 for r in evaluation_results if r.get('success', False))
    elements.append(Paragraph(f"<b>Total Sections Evaluated:</b> {total_sections}", styles['Normal']))
    elements.append(Paragraph(f"<b>Successful Evaluations:</b> {successful_evaluations}", styles['Normal']))
    elements.append(Spacer(1, 0.3*inch))
    
    # Process each section
    for section in sections_data:
        section_index = section.get('index', 'N/A')
        section_title = section.get('title', 'Untitled Section')
        section_content = section.get('content', '')
        rubric = section.get('rubric', '')
        
        # Section header
        section_header = Paragraph(f"Section {section_index}: {section_title}", section_heading_style)
        elements.append(section_header)
        elements.append(Spacer(1, 0.1*inch))
        
        # Section content preview
        if section_content:
            content_preview = section_content[:500] + "..." if len(section_content) > 500 else section_content
            elements.append(Paragraph("<b>Section Content Preview:</b>", styles['Normal']))
            content_para = Paragraph(content_preview.replace('\n', '<br/>'), styles['Normal'])
            elements.append(content_para)
            elements.append(Spacer(1, 0.15*inch))
        
        # Rubric used - REMOVED per user request
        # if rubric:
        #     elements.append(Paragraph("<b>Rubric Used:</b>", styles['Normal']))
        #     rubric_para = Paragraph(rubric[:1000].replace('\n', '<br/>') + ("..." if len(rubric) > 1000 else ""), styles['Normal'])
        #     elements.append(rubric_para)
        #     elements.append(Spacer(1, 0.15*inch))
        
        # Find corresponding evaluation result
        result = next((r for r in evaluation_results if str(r.get('section_index')) == str(section_index)), None)
        
        if result and result.get('success') and result.get('result'):
            # Evaluation results table
            elements.append(Paragraph("<b>Evaluation Results:</b>", styles['Normal']))
            elements.append(Spacer(1, 0.1*inch))
            
            # Parse markdown table
            table_data = parse_markdown_table(result.get('result', ''))
            
            if table_data and table_data.get('headers') and table_data.get('rows'):
                # Create table
                table_rows = [table_data['headers']] + table_data['rows']
                
                # Convert to Paragraph objects for better formatting
                formatted_rows = []
                for row in table_rows:
                    formatted_row = []
                    for cell in row:
                        # Clean up markdown formatting
                        cell_text = cell.replace('**', '').replace('*', '')
                        formatted_row.append(Paragraph(cell_text, styles['Normal']))
                    formatted_rows.append(formatted_row)
                
                # Create table
                table = Table(formatted_rows, colWidths=[2*inch, 0.8*inch, 2.5*inch, 2.2*inch])
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 11),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                    ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
                ]))
                
                elements.append(table)
            else:
                # Fallback: display as text if table parsing fails
                result_text = result.get('result', '').replace('\n', '<br/>')
                elements.append(Paragraph(result_text, styles['Normal']))
        elif result and not result.get('success'):
            # Error case
            error_msg = result.get('error', 'Unknown error occurred')
            elements.append(Paragraph(f"<b>Evaluation Error:</b> {error_msg}", styles['Normal']))
        else:
            elements.append(Paragraph("<i>No evaluation result available for this section.</i>", styles['Italic']))
        
        elements.append(Spacer(1, 0.2*inch))
        elements.append(PageBreak())
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer


@app.route('/export-pdf', methods=['POST'])
def export_pdf():
    """Export evaluation results as PDF"""
    logger.info("Export PDF endpoint called")
    
    try:
        data = request.get_json()
        
        if not data:
            logger.warning("No data provided in request")
            return jsonify({'error': 'No data provided'}), 400
        
        sections_data = data.get('sections', [])
        evaluation_results = data.get('results', [])
        
        if not sections_data:
            logger.warning("No sections provided")
            return jsonify({'error': 'No sections provided'}), 400
        
        if not evaluation_results:
            logger.warning("No evaluation results provided")
            return jsonify({'error': 'No evaluation results provided'}), 400
        
        logger.info(f"Generating PDF report for {len(sections_data)} sections")
        
        # Generate PDF
        pdf_buffer = generate_pdf_report(sections_data, evaluation_results)
        
        # Create filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"RFP_Evaluation_Report_{timestamp}.pdf"
        
        logger.info(f"PDF report generated successfully: {filename}")
        
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
    
    except Exception as e:
        logger.error(f"Error generating PDF: {str(e)}", exc_info=True)
        return jsonify({
            'error': f'Error generating PDF: {str(e)}'
        }), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Starting Flask application on port {port}, debug={debug_mode}")
    logger.info(f"Environment: PORT={port}, FLASK_DEBUG={debug_mode}")
    
    app.run(debug=debug_mode, host='0.0.0.0', port=port)

