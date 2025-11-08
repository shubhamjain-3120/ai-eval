import os
import json
from openai import OpenAI
from openai import AuthenticationError, RateLimitError, APIError

# Initialize OpenAI client
api_key = os.environ.get('OPENAI_API_KEY')
if not api_key:
    raise ValueError("OPENAI_API_KEY environment variable is not set")

client = OpenAI(api_key=api_key)


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
    
    # Call OpenAI API
    response = client.chat.completions.create(
        model="gpt-5",
        messages=[
            {"role": "system", "content": "You are an expert RFP evaluator. You MUST always format your responses as markdown tables with columns: Metric, Score, Reasoning, Fix Prompt. Never provide plain text or other formats - only markdown tables."},
            {"role": "user", "content": prompt}
        ]
    )
    
    # Extract the response text
    result = response.choices[0].message.content
    
    # Validate table format
    if not is_markdown_table(result):
        if retry_count < 1:  # Retry once with stronger prompt
            return evaluate_single_section(rfp_text, rubric_text, retry_count + 1)
        else:
            # Try to extract table from response if it exists but wasn't detected
            lines = result.split('\n')
            table_lines = [line for line in lines if line.strip().startswith('|') and line.strip().endswith('|')]
            if len(table_lines) >= 2:
                # Found some table rows, return just those
                return '\n'.join(table_lines)
    
    return result


def handler(event, context):
    """Netlify serverless function handler"""
    # Handle CORS
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Content-Type': 'application/json'
    }
    
    # Handle preflight OPTIONS request
    if event['httpMethod'] == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': headers,
            'body': ''
        }
    
    # Only allow POST requests
    if event['httpMethod'] != 'POST':
        return {
            'statusCode': 405,
            'headers': headers,
            'body': json.dumps({'error': 'Method not allowed'})
        }
    
    try:
        # Parse request body
        if not event.get('body'):
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'error': 'No data provided'})
            }
        
        data = json.loads(event['body'])
        
        # Support both old format (single section) and new format (multiple sections)
        sections = data.get('sections', [])
        
        # If sections array is empty, check for old format
        if not sections:
            rfp_text = data.get('rfp_text', '').strip()
            rubric_text = data.get('rubric', '').strip()
            if rfp_text and rubric_text:
                sections = [{'rfp_text': rfp_text, 'rubric': rubric_text}]
        
        if not sections:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'error': 'No sections provided'})
            }
        
        # Validate all sections
        for i, section in enumerate(sections):
            rfp_text = section.get('rfp_text', '').strip()
            rubric_text = section.get('rubric', '').strip()
            
            if not rfp_text:
                return {
                    'statusCode': 400,
                    'headers': headers,
                    'body': json.dumps({'error': f'RFP text is required for section {i + 1}'})
                }
            
            if not rubric_text:
                return {
                    'statusCode': 400,
                    'headers': headers,
                    'body': json.dumps({'error': f'Rubric is required for section {i + 1}'})
                }
        
        # Process sections sequentially
        results = []
        for i, section in enumerate(sections):
            rfp_text = section.get('rfp_text', '').strip()
            rubric_text = section.get('rubric', '').strip()
            
            try:
                evaluation_result = evaluate_single_section(rfp_text, rubric_text)
                results.append({
                    'section_index': i,
                    'success': True,
                    'result': evaluation_result
                })
            except AuthenticationError:
                results.append({
                    'section_index': i,
                    'success': False,
                    'error': 'OpenAI API authentication failed. Please check that your OPENAI_API_KEY environment variable is correct and valid. Make sure there are no extra spaces or quotes around the key.'
                })
            except RateLimitError:
                results.append({
                    'section_index': i,
                    'success': False,
                    'error': 'OpenAI API rate limit exceeded. Please try again in a moment.'
                })
            except APIError as api_error:
                error_msg = str(api_error)
                if "insufficient_quota" in error_msg.lower() or "quota" in error_msg.lower():
                    results.append({
                        'section_index': i,
                        'success': False,
                        'error': 'OpenAI API quota exceeded. Please check your OpenAI account billing and usage limits.'
                    })
                else:
                    results.append({
                        'section_index': i,
                        'success': False,
                        'error': f'OpenAI API error: {error_msg}'
                    })
            except Exception as api_error:
                error_msg = str(api_error)
                # Fallback for other error types
                if "401" in error_msg or "authentication" in error_msg.lower() or "invalid_api_key" in error_msg.lower() or "access denied" in error_msg.lower():
                    results.append({
                        'section_index': i,
                        'success': False,
                        'error': 'OpenAI API authentication failed. Please check that your OPENAI_API_KEY environment variable is correct and valid. Make sure there are no extra spaces or quotes around the key.'
                    })
                else:
                    results.append({
                        'section_index': i,
                        'success': False,
                        'error': f'OpenAI API error: {error_msg}'
                    })
        
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({
                'success': True,
                'results': results
            })
        }
    
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({
                'error': f'An error occurred: {str(e)}'
            })
        }

