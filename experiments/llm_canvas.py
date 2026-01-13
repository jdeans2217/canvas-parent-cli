import os
import requests
import logging
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration
CANVAS_API_URL = os.getenv("CANVAS_API_URL", "https://yourschool.instructure.com")
CANVAS_API_KEY = os.getenv("CANVAS_API_KEY")
STUDENT_ID = os.getenv("STUDENT_ID")  # Example student ID

# Validate environment variables
missing_vars = []
if not CANVAS_API_KEY:
    missing_vars.append("CANVAS_API_KEY")
if not STUDENT_ID:
    missing_vars.append("STUDENT_ID")

if missing_vars:
    raise EnvironmentError(f"Missing environment variables: {', '.join(missing_vars)}. Please ensure they are set in the .env file.")

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Headers for Canvas API
headers = {
    "Authorization": f"Bearer {CANVAS_API_KEY}",
    "Accept": "application/json"
}

# Ollama API configuration
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")

def get_student_courses(student_id):
    """Fetches course information for a specific student."""
    endpoint = f"{CANVAS_API_URL}/api/v1/users/{student_id}/courses"
    logger.debug(f"Making request to: {endpoint} with headers: {headers}")
    try:
        response = requests.get(endpoint, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred: {http_err} - Response: {response.text}")
    except Exception as err:
        logger.error(f"An error occurred: {err}")
    return []

def get_course_assignments(course_id):
    """Fetches assignments for a given course."""
    endpoint = f"{CANVAS_API_URL}/api/v1/courses/{course_id}/assignments"
    logger.debug(f"Making request to: {endpoint} with headers: {headers}")
    try:
        response = requests.get(endpoint, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred: {http_err} - Response: {response.text}")
    except Exception as err:
        logger.error(f"An error occurred: {err}")
    return []

def formulate_prompt(user_question):
    """Creates a prompt for the LLM to determine the necessary API calls."""
    prompt = f"""
You are an assistant that helps users retrieve information from the Canvas LMS API based on their questions.

Given the user's question, determine which API endpoints to call and provide the necessary parameters.

Respond with a JSON object following this structure:

{{
    "endpoint": "string",  # e.g., "get_student_courses" or "get_course_assignments"
    "params": {{
        "key1": "value1",
        "key2": "value2",
        ...
    }}
}}

If the question requires multiple API calls, provide a list of such JSON objects.

User Question: "{user_question}"
"""
    return prompt

def get_llm_response(prompt):
    """Sends the prompt to the Ollama API and retrieves the response."""
    try:
        response = requests.post(
            OLLAMA_API_URL,
            json={"model": "llama3.2:latest", "prompt": prompt, "stream": false},
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        return response.json().get('response', '').strip()
    except Exception as e:
        logger.error(f"Ollama API error: {e}")
        return None

def execute_api_calls(api_calls):
    """Executes the determined API calls and collects the data."""
    results = {}
    for call in api_calls:
        endpoint = call.get("endpoint")
        params = call.get("params", {})
        if endpoint == "get_student_courses":
            student_id = params.get("student_id", STUDENT_ID)
            if student_id:
                courses = get_student_courses(student_id)
                results["courses"] = courses
            else:
                logger.warning("Missing 'student_id' parameter for 'get_student_courses' endpoint.")
        elif endpoint == "get_course_assignments":
            course_id = params.get("course_id")
            if course_id:
                assignments = get_course_assignments(course_id)
                if "assignments" not in results:
                    results["assignments"] = {}
                results["assignments"][course_id] = assignments
            else:
                logger.warning("Missing 'course_id' parameter for 'get_course_assignments' endpoint.")
        else:
            logger.warning(f"Unknown endpoint: {endpoint}")
    return results

def formulate_answer(api_results, api_calls):
    """Formats the API results into a user-friendly answer."""
    answer = ""
    for call in api_calls:
        endpoint = call.get("endpoint")
        params = call.get("params", {})
        if endpoint == "get_student_courses":
            courses = api_results.get("courses", [])
            if not courses:
                answer += "No active courses found for the specified student.\n"
            else:
                answer += "Active Courses:\n"
                for course in courses:
                    course_id = course.get("id", "N/A")
                    course_name = course.get("name", "N/A")
                    answer += f"- {course_name} (ID: {course_id})\n"
        elif endpoint == "get_course_assignments":
            course_id = params.get("course_id")
            assignments = api_results.get("assignments", {}).get(course_id, [])
            if not assignments:
                answer += f"No assignments found for course ID {course_id}.\n"
            else:
                answer += f"Assignments for Course ID {course_id}:\n"
                for assignment in assignments:
                    assignment_name = assignment.get("name", "N/A")
                    due_at = assignment.get("due_at", "No due date")
                    answer += f"  - {assignment_name} (Due: {due_at})\n"
    return answer if answer else "I'm sorry, I couldn't retrieve the information you requested."

def process_user_question(user_question):
    """Handles the entire process of interpreting the question, making API calls, and formulating an answer."""
    prompt = formulate_prompt(user_question)
    logger.debug(f"LLM Prompt:\n{prompt}")
    
    llm_response = get_llm_response(prompt)
    if not llm_response:
        return "I'm sorry, I couldn't process your request at the moment."

    logger.debug(f"LLM Response:\n{llm_response}")

    # Attempt to parse the LLM response as JSON
    try:
        api_calls = json.loads(llm_response)
        # Ensure api_calls is a list for uniform processing
        if isinstance(api_calls, dict):
            api_calls = [api_calls]
        elif not isinstance(api_calls, list):
            raise ValueError("API calls should be a JSON object or a list of JSON objects.")
    except json.JSONDecodeError:
        logger.error("Failed to parse LLM response as JSON.")
        return "I'm sorry, I couldn't understand your request."
    except ValueError as ve:
        logger.error(f"Invalid LLM response format: {ve}")
        return "I'm sorry, the assistant couldn't process your request correctly."

    # Execute the determined API calls
    api_results = execute_api_calls(api_calls)

    # Formulate the final answer
    answer = formulate_answer(api_results, api_calls)
    return answer

def main():
    print("Welcome to the Canvas Assistant! Ask me anything about your courses or assignments.")
    while True:
        user_question = input("\nYour Question (or type 'exit' to quit): ")
        if user_question.strip().lower() in ['exit', 'quit']:
            print("Goodbye!")
            break
        if not user_question.strip():
            print("Please enter a valid question.")
            continue
        answer = process_user_question(user_question)
        print("\nAnswer:")
        print(answer)

if __name__ == "__main__":
    main()
