import os
from flask import Flask, render_template, request, jsonify
from openai import OpenAI
from openai import AuthenticationError, RateLimitError, APIError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Initialize OpenAI client
api_key = os.getenv('OPENAI_API_KEY')
if not api_key:
    raise ValueError("OPENAI_API_KEY environment variable is not set")

client = OpenAI(api_key=api_key)


@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')


def evaluate_single_section(rfp_text, rubric_text):
    """Helper function to evaluate a single section"""
    # Construct the prompt
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


Format your response as a table with columns: Metric, Score, Reasoning, Fix Prompt."""
    
    # Call OpenAI API
    response = client.chat.completions.create(
        model="gpt-5",
        messages=[
            {"role": "system", "content": "You are an expert RFP evaluator. Provide detailed, structured evaluations with scores, reasoning, and actionable fix suggestions."},
            {"role": "user", "content": prompt}
        ]
    )
    
    # Extract the response text
    return response.choices[0].message.content


@app.route('/evaluate', methods=['POST'])
def evaluate():
    """Evaluate RFP response sections against rubrics"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Support both old format (single section) and new format (multiple sections)
        sections = data.get('sections', [])
        
        # If sections array is empty, check for old format
        if not sections:
            rfp_text = data.get('rfp_text', '').strip()
            rubric_text = data.get('rubric', '').strip()
            if rfp_text and rubric_text:
                sections = [{'rfp_text': rfp_text, 'rubric': rubric_text}]
        
        if not sections:
            return jsonify({'error': 'No sections provided'}), 400
        
        # Validate all sections
        for i, section in enumerate(sections):
            rfp_text = section.get('rfp_text', '').strip()
            rubric_text = section.get('rubric', '').strip()
            
            if not rfp_text:
                return jsonify({'error': f'RFP text is required for section {i + 1}'}), 400
            
            if not rubric_text:
                return jsonify({'error': f'Rubric is required for section {i + 1}'}), 400
        
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
                    'error': 'OpenAI API authentication failed. Please check that your OPENAI_API_KEY in the .env file is correct and valid. Make sure there are no extra spaces or quotes around the key.'
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
                        'error': 'OpenAI API authentication failed. Please check that your OPENAI_API_KEY in the .env file is correct and valid. Make sure there are no extra spaces or quotes around the key.'
                    })
                else:
                    results.append({
                        'section_index': i,
                        'success': False,
                        'error': f'OpenAI API error: {error_msg}'
                    })
        
        return jsonify({
            'success': True,
            'results': results
        })
    
    except Exception as e:
        return jsonify({
            'error': f'An error occurred: {str(e)}'
        }), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)

