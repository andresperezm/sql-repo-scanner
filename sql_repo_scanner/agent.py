import logging
import tempfile
import git
import re
import os
import shutil
import json

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.tools.tool_context import ToolContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

async def clone_git_repo(repo_url: str, tool_context: ToolContext) -> dict:
    """Clones a Git repository from a given SSH URL into a temporary directory.

    Args:
        repo_url: The SSH URL of the Git repository to clone.
        tool_context: The context object for the agent tool, used to store
                      repository information like path, owner, and name.

    Returns:
        A dictionary indicating the status of the operation ('success' or 'failure')
        and a message. If successful, repository info is stored in tool_context.state.
    """
    logger.info(f"Attempting to clone repository via SSH: {repo_url}")

    ssh_url_pattern = r"git@[\w.-]+:([\w.-]+)/([\w.-]+?)(?:\.git)?$"
    match = re.search(ssh_url_pattern, repo_url)

    if not match:
        err_msg = f"Invalid or unsupported SSH repository URL format: {repo_url}. Expected format like 'git@hostname:owner/repo.git'."
        logger.error(err_msg)
        return {
            "status": "failure",
            "message": err_msg,
        }

    repo_owner = match.group(1)
    repo_name = match.group(2)
    repo_path = None

    try:
        repo_path = tempfile.mkdtemp(prefix=f"repo_{repo_owner}_{repo_name}_")
        logger.info(f"Created temporary directory for cloning: {repo_path}")
        logger.info(f"Cloning {repo_url} into {repo_path}...")

        git.Repo.clone_from(repo_url, repo_path)
        logger.info(f"Successfully cloned {repo_name} from {repo_owner} to {repo_path}")
        tool_context.state['repo_url'] = repo_url
        tool_context.state['repo_owner'] = repo_owner
        tool_context.state['repo_name'] = repo_name
        tool_context.state['repo_path'] = repo_path
        tool_context.state['repository_analysis'] = {}

        return {
            "status": "success",
            "message": f"Successfully cloned {repo_name} repository. Repo information stored in agent context."
        }
    except (git.GitError, Exception) as e:
        error_type = "Git command error" if isinstance(e, git.GitError) else "Unexpected error"
        logger.error(f"{error_type} during cloning of {repo_url}: {e}")
        if repo_path and os.path.exists(repo_path):
            try:
                shutil.rmtree(repo_path)
                logger.info(f"Cleaned up temporary directory {repo_path} after failed clone.")
            except Exception as cleanup_exc:
                logger.error(f"Failed to cleanup temporary directory {repo_path}: {cleanup_exc}")
        return {
            "status": "failure",
            "message": f"{error_type}: {str(e)}",
        }


async def list_repo_files(tool_context: ToolContext) -> dict:
    """Lists all files in the cloned repository, excluding the .git directory.

    It populates the tool_context.state['repository_analysis'] dictionary
    with entries for each file, marking them as not yet scanned.

    Args:
        tool_context: The context object for the agent tool, containing the
                      local path to the cloned repository ('repo_path') and
                      the 'repository_analysis' state dictionary.

    Returns:
        A dictionary indicating the status ('success' or 'failure'),
        a message, and if successful, a list of relative file paths found.
    """
    local_repo_path = tool_context.state.get('repo_path')
    logger.info(f"Attempting to list files recursively in path: {local_repo_path}, storing relative paths.")

    if not os.path.exists(local_repo_path):
        err_msg = f"Error: Path does not exist: {local_repo_path}"
        logger.error(err_msg)
        return {
            "status": "failure",
            "message": err_msg
        }

    if not os.path.isdir(local_repo_path):
        err_msg = f"Error: Path is not a directory: {local_repo_path}"
        logger.error(err_msg)
        return {
            "status": "failure",
            "message": err_msg
        }

    if 'repository_analysis' not in tool_context.state:
        tool_context.state['repository_analysis'] = {}

    try:
        files_to_scan = []
        for root, dirnames, files in os.walk(local_repo_path):
            if '.git' in dirnames:
                dirnames.remove('.git')

            for file in files:
                full_path = os.path.join(root, file)
                relative_path = os.path.relpath(full_path, local_repo_path)
                tool_context.state['repository_analysis'][relative_path] = {
                    "sql_statements": [],
                    "scanned": False
                }
                files_to_scan.append(relative_path)
        
        logger.info(f"Found and initialized {len(files_to_scan)} files in {local_repo_path} within repository_analysis state.")
        return {
            "status": "success",
            "files": files_to_scan,
            "message": f"Fount {len(files_to_scan)} files to scan. File list stored in agent context.",
        }
    except Exception as e:
        err_msg = f"Error listing files in {local_repo_path}: {e}"
        logger.error(err_msg)
        return {
            "status": "failure",
            "message": err_msg,
            "directory_path": local_repo_path
        }


async def get_file_content(relative_file_path: str, tool_context: ToolContext) -> dict:
    """Reads and returns the content of a specified file within the cloned repository.

    Args:
        relative_file_path: The relative path of the file (from the repository root)
                            whose content is to be read.
        tool_context: The context object for the agent tool, containing the
                      local path to the cloned repository.

    Returns:
        A dictionary indicating the status ('success' or 'failure'), a message,
        and if successful, the content of the file as a string.
    """
    local_repo_path = tool_context.state.get('repo_path')
    if not local_repo_path:
        err_msg = "Error: 'repo_path' not found in tool_context.state. Cannot resolve relative path."
        logger.error(err_msg)
        return {"status": "failure", "message": err_msg}

    absolute_file_path = os.path.join(local_repo_path, relative_file_path)
    logger.info(f"Attempting to read content of file: {absolute_file_path} (relative: {relative_file_path})")

    if not os.path.exists(absolute_file_path):
        err_msg = f"Error: File does not exist: {absolute_file_path}"
        logger.error(err_msg)
        return {"status": "failure", "message": err_msg}

    if not os.path.isfile(absolute_file_path):
        err_msg = f"Error: Path is not a file: {absolute_file_path}"
        logger.error(err_msg)
        return {"status": "failure", "message": err_msg}

    try:
        with open(absolute_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        logger.info(f"Successfully read content of file: {absolute_file_path}")
        return {
            "status": "success",
            "message": "Successfully read file content.",
            "content": content,
        }
    except Exception as e:
        err_msg = f"Error reading file {absolute_file_path}: {e}"
        logger.error(err_msg)
        return {"status": "failure", "message": err_msg}


async def save_sql_statements(relative_file_path: str, sql_statements: list, tool_context: ToolContext) -> dict:
    """Saves a list of SQL statements found in a file to the tool_context.state.

    It updates the 'repository_analysis' entry for the given file with the
    provided SQL statements and marks the file as 'scanned'.

    Args:
        relative_file_path: The relative path of the file for which SQL statements are being saved.
        sql_statements: A list of SQL statement strings found in the file.
        tool_context: The context object for the agent tool.

    Returns:
        A dictionary indicating the status ('success' or 'failure') and a message.
    """
    if 'repository_analysis' not in tool_context.state:
        err_msg = "Error: 'repository_analysis' not found in tool_context.state. Cannot save SQL statement."
        logger.error(err_msg)
        return {"status": "failure", "message": err_msg}

    if relative_file_path not in tool_context.state['repository_analysis']:
        logger.warning(f"File path {relative_file_path} not found in repository_analysis during save_sql_statement. Initializing with pending status.")
        tool_context.state['repository_analysis'][relative_file_path] = {
            "sql_statements": [],
            "scanned": False
        }
    
    tool_context.state['repository_analysis'][relative_file_path]['sql_statements'] = sql_statements
    tool_context.state['repository_analysis'][relative_file_path]['scanned'] = True
    logger.info(f"Saved SQL statements for {relative_file_path}. Statements count: {len(tool_context.state['repository_analysis'][relative_file_path]['sql_statements'])}")
    return {"status": "success", "message": "statement saved"}

async def mark_file_as_scanned(relative_file_path: str, tool_context: ToolContext) -> dict:
    """Marks a specific file in the repository analysis as scanned.

    If the file is not already in the repository_analysis, it will be added.

    Args:
        relative_file_path: The relative path of the file to be marked as scanned.
        tool_context: The context object for the agent tool, containing the
                      repository_analysis state.

    Returns:
        A dictionary with the status of the operation and a message.
    """
    if 'repository_analysis' not in tool_context.state:
        err_msg = "Error: 'repository_analysis' not found in tool_context.state. Cannot save mark file as scanned."
        logger.error(err_msg)
        return {"status": "failure", "message": err_msg}

    if relative_file_path not in tool_context.state['repository_analysis']:
        logger.warning(f"File path {relative_file_path} not found in repository_analysis during save_sql_statement. Initializing with pending status.")
        tool_context.state['repository_analysis'][relative_file_path] = {
            "sql_statements": [],
            "scanned": True
        }
    
    tool_context.state['repository_analysis'][relative_file_path]['scanned'] = True
    message = f"{relative_file_path} marked as scanned."
    logger.info(message)
    return {"status": "success", "message": message}


async def are_all_files_scanned(tool_context: ToolContext) -> dict:
    """Checks if all files listed in tool_context.state['repository_analysis'] have been scanned.

    Args:
        tool_context: The context object for the agent tool, containing the
                      'repository_analysis' dictionary.

    Returns:
        A dictionary indicating the status ('success' or 'failure'), a message,
        and a boolean 'all_files_scanned' which is True if all files are scanned, False otherwise.
    """
    logger.info("Checking if all files have been scanned.")
    if 'repository_analysis' not in tool_context.state:
        err_msg = "Error: 'repository_analysis' not found in tool_context.state. Cannot determine if all files were scanned."
        logger.error(err_msg)
        return {"status": "failure", "message": err_msg, "all_files_scanned": False}

    repository_analysis = tool_context.state['repository_analysis']
    if not repository_analysis:
        logger.info("No files found in repository_analysis. Considering all (zero) files scanned.")
        return {"status": "success", "message": "No files to scan.", "all_files_scanned": True}

    for file_path, details in repository_analysis.items():
        if not details.get('scanned', False):
            logger.info(f"File {file_path} has not been scanned yet.")
            return {"status": "success", "message": "Not all files have been scanned.", "all_files_scanned": False}

    logger.info("All files have been successfully scanned.")
    return {"status": "success", "message": "All files have been scanned.", "all_files_scanned": True}


async def generate_repository_analysis_jsonl(tool_context: ToolContext) -> dict:
    """Generates a JSONL file containing the repository analysis data.

    The file will be named '{repo_name}_analysis.jsonl' and saved in the
    current working directory. Each line in the file will be a JSON object
    representing the analysis for a single file.

    Args:
        tool_context: The context object for the agent tool, containing
                      'repository_analysis' and 'repo_name' in its state.

    Returns:
        A dictionary indicating the status ('success' or 'failure'),
        a message, and if successful, the path to the generated JSONL file.
    """
    logger.info("Attempting to generate repository analysis JSONL file.")

    repo_name = tool_context.state.get('repo_name')
    if not repo_name:
        err_msg = "Error: 'repo_name' not found in tool_context.state. Cannot name the output file."
        logger.error(err_msg)
        return {"status": "failure", "message": err_msg}

    repository_analysis = tool_context.state.get('repository_analysis')
    if repository_analysis is None: # Check for None explicitly, as empty dict is valid
        err_msg = "Error: 'repository_analysis' not found in tool_context.state. Cannot generate report."
        logger.error(err_msg)
        return {"status": "failure", "message": err_msg}

    if not repository_analysis:
        logger.info("repository_analysis is empty. Generating an empty JSONL file.")

    output_file_name = f"{repo_name}_analysis.jsonl"
    output_file_path = os.path.join(os.getcwd(), output_file_name)

    try:
        with open(output_file_path, 'w', encoding='utf-8') as f:
            for file_path, details in repository_analysis.items():
                record = {"file_path": file_path, **details}
                json.dump(record, f)
                f.write('\n')
        
        success_msg = f"Successfully generated repository analysis JSONL file: {output_file_path}"
        logger.info(success_msg)
        return {
            "status": "success",
            "message": success_msg,
            "output_file_path": output_file_path
        }
    except IOError as e:
        err_msg = f"IOError generating JSONL file {output_file_path}: {e}"
        logger.error(err_msg)
        return {"status": "failure", "message": err_msg}
    except Exception as e:
        err_msg = f"Unexpected error generating JSONL file {output_file_path}: {e}"
        logger.error(err_msg)
        return {"status": "failure", "message": err_msg}


FILE_SCAN_AGENT_NAME = "file_sql_extractor_agent"
FILE_SCAN_MODEL = "gemini-2.0-flash"
FILE_SCAN_INSTRUCTION = (
    "You are an AI Agent specializing in identifying SQL statements embedded in various files. "
    "You have a list of files stored in your context. Your task is to use the get_file_content tool to get the file content for each file, meticulously scan the file content, and then use the save_sql_statements tool to save all SQL statements fount. "
    "These file content may be written in any programming language (e.g., Python, Java, C#, etc.), or embedded within configuration files like (e.g. *.properties, *.xml, *.json, *.yaml, etc.).\n\n"
    "Focus on extracting the raw SQL query strings that are intended to be executed against a database. "
    "Ensure you capture SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, and any other common SQL commands. "
    "For each file return only the SQL statements themselves, each as a separate item in a list."
)
sql_scanner_agent = Agent(
    name=FILE_SCAN_AGENT_NAME,
    model=FILE_SCAN_MODEL,
    instruction=FILE_SCAN_INSTRUCTION,
    tools=[
        get_file_content,
        save_sql_statements,
    ]
)

ROOT_AGENT_NAME = "sql_repo_scan_agent"
ROOT_AGENT_MODEL = "gemini-2.0-flash"
ROOT_AGENT_INSTRUCTION = (
    "You are a specialized AI Agent for finding SQL scripts within a Github repository. "
    "Your goal is to clone the repository using the clone_git_repo tool, list the files in the repository using the list_repo_files tool, and then call multiple sql_scanner_agent agent to scan the files, use the are_all_files_scanned tool to check if all files has been scanned. when all files are scanned use the generate_repository_analysis_jsonl tool to generate a jsonl file.\n\n"
)
root_agent = Agent(
    name=ROOT_AGENT_NAME,
    model=ROOT_AGENT_MODEL,
    instruction=ROOT_AGENT_INSTRUCTION,
    tools=[
        clone_git_repo,
        list_repo_files,
        are_all_files_scanned,
        generate_repository_analysis_jsonl
    ],
    sub_agents=[sql_scanner_agent]
)
