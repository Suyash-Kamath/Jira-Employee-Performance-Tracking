import requests
import base64
import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Jira credentials
JIRA_DOMAIN = 'probustech.atlassian.net'
JIRA_EMAIL = 'suyash.kamath@probusinsurance.com'
JIRA_API_TOKEN = os.getenv('JIRA_API_TOKEN')

# Base64 encode email:token
auth_string = f'{JIRA_EMAIL}:{JIRA_API_TOKEN}'.encode('utf-8')
AUTH = base64.b64encode(auth_string).decode('utf-8')

HEADERS = {
    'Authorization': f'Basic {AUTH}',
    'Accept': 'application/json'
}

# Get all projects
def get_projects():
    url = f'https://{JIRA_DOMAIN}/rest/api/3/project/search'
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    data = response.json()
    return [{'key': p['key'], 'name': p['name']} for p in data.get('values', [])]

# Get assignees in a project
def get_project_assignees(project_key):
    url = f'https://{JIRA_DOMAIN}/rest/api/3/search'
    params = {
        'jql': f'project={project_key}',
        'fields': 'assignee,summary,status',
        'maxResults': 100
    }
    response = requests.get(url, headers=HEADERS, params=params)
    response.raise_for_status()
    data = response.json()
    
    assignee_map = {}
    for issue in data.get('issues', []):
        fields = issue.get('fields', {})
        assignee = fields.get('assignee')
        if assignee:
            name = assignee.get('displayName')
            if name not in assignee_map:
                assignee_map[name] = []
            assignee_map[name].append({
                'task': fields.get('summary'),
                'status': fields.get('status', {}).get('name')
            })
    return assignee_map

# CLI interaction
def run_cli():
    try:
        projects = get_projects()
    except Exception as e:
        print(f"❌ Failed to fetch projects: {e}")
        return

    print("\n🔧 Select a project by number:")
    for i, proj in enumerate(projects):
        print(f"{i + 1}. {proj['name']} ({proj['key']})")

    try:
        choice = int(input("\nEnter your choice (1-N): ")) - 1
        if 0 <= choice < len(projects):
            project_key = projects[choice]['key']
            try:
                assignee_map = get_project_assignees(project_key)
            except Exception as e:
                print(f"❌ Failed to fetch assignees: {e}")
                return

            employee_names = list(assignee_map.keys())
            if not employee_names:
                print("⚠️  No employees found for this project.")
                return

            print(f"\n✅ Employees in project '{projects[choice]['name']}':")
            for i, name in enumerate(employee_names):
                print(f"{i + 1}. {name}")

            emp_choice = int(input("\nSelect an employee number to view their tasks: ")) - 1
            if 0 <= emp_choice < len(employee_names):
                selected_emp = employee_names[emp_choice]
                print(f"\n📋 Tasks for {selected_emp}:")
                for task in assignee_map[selected_emp]:
                    print(f"- {task['task']}: {task['status']}")
            else:
                print("❌ Invalid employee selected.")
        else:
            print("❌ Invalid project selection.")
    except ValueError:
        print("❌ Please enter a valid number.")

# Run the CLI
if __name__ == '__main__':
    run_cli()
