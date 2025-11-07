import os
import logging
import sys
from flask import Flask, render_template, request, jsonify
from openai import OpenAI
from openai import AuthenticationError, RateLimitError, APIError
from dotenv import load_dotenv
from datetime import datetime

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

# Initialize OpenAI client
api_key = os.getenv('OPENAI_API_KEY')
if not api_key:
    logger.error("OPENAI_API_KEY environment variable is not set")
    raise ValueError("OPENAI_API_KEY environment variable is not set")

logger.info("Initializing OpenAI client")
client = OpenAI(api_key=api_key)
logger.info("OpenAI client initialized successfully")


@app.route('/')
def index():
    """Render the main page"""
    logger.info("Index page requested")
    return render_template('index.html')


def evaluate_single_section(rfp_text, rubric_text):
    """Helper function to evaluate a single section"""
    logger.debug(f"Evaluating section - RFP text length: {len(rfp_text)}, Rubric length: {len(rubric_text)}")
    
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
    
    logger.debug(f"Prompt constructed, length: {len(prompt)}")
    logger.info("Calling OpenAI API...")
    
    try:
        # Call OpenAI API
        start_time = datetime.now()
        response = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": "You are an expert RFP evaluator. Provide detailed, structured evaluations with scores, reasoning, and actionable fix suggestions."},
                {"role": "user", "content": prompt}
            ]
        )
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.info(f"OpenAI API call completed in {duration:.2f} seconds")
        
        # Extract the response text
        result = response.choices[0].message.content
        logger.debug(f"Response received, length: {len(result)}")
        
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
                results.append({
                    'section_index': i,
                    'success': True,
                    'result': evaluation_result
                })
            except AuthenticationError as e:
                logger.error(f"Section {i + 1}: Authentication error - {str(e)}")
                results.append({
                    'section_index': i,
                    'success': False,
                    'error': 'OpenAI API authentication failed. Please check that your OPENAI_API_KEY environment variable is correct and valid. Make sure there are no extra spaces or quotes around the key.'
                })
            except RateLimitError as e:
                logger.warning(f"Section {i + 1}: Rate limit error - {str(e)}")
                results.append({
                    'section_index': i,
                    'success': False,
                    'error': 'OpenAI API rate limit exceeded. Please try again in a moment.'
                })
            except APIError as api_error:
                error_msg = str(api_error)
                logger.error(f"Section {i + 1}: API error - {error_msg}")
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
                logger.error(f"Section {i + 1}: Unexpected error - {error_msg}", exc_info=True)
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


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Starting Flask application on port {port}, debug={debug_mode}")
    logger.info(f"Environment: PORT={port}, FLASK_DEBUG={debug_mode}")
    
    app.run(debug=debug_mode, host='0.0.0.0', port=port)

