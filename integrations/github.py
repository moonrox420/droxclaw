import os
from github import Github
from typing import Optional, List
from langchain_core.tools import tool

class GitHubIntegration:
    def __init__(self):
        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token:
            raise ValueError("GITHUB_TOKEN not found in environment variables")
        self.github = Github(github_token)
        
    @tool
    def list_repos(self) -> str:
        """List all repositories for the authenticated user"""
        try:
            repos = []
            for repo in self.github.get_user().get_repos():
                repos.append({
                    'name': repo.name,
                    'url': repo.html_url,
                    'description': repo.description
                })
            return f"Repositories: {repos}"
        except Exception as e:
            return f"Error listing repositories: {str(e)}"
            
    @tool
    def create_issue(self, repo_name: str, title: str, body: str) -> str:
        """Create an issue in a repository"""
        try:
            user = self.github.get_user()
            repo = user.get_repo(repo_name)
            issue = repo.create_issue(title=title, body=body)
            return f"Issue created: {issue.html_url}"
        except Exception as e:
            return f"Error creating issue: {str(e)}"
            
    @tool
    def get_issues(self, repo_name: str) -> str:
        """Get open issues from a repository"""
        try:
            user = self.github.get_user()
            repo = user.get_repo(repo_name)
            issues = []
            for issue in repo.get_issues(state='open'):
                issues.append({
                    'title': issue.title,
                    'url': issue.html_url,
                    'created_at': issue.created_at.isoformat()
                })
            return f"Open issues: {issues}"
        except Exception as e:
            return f"Error getting issues: {str(e)}"

def get_github_tools():
    """Return GitHub tools for the agent"""
    try:
        github_integration = GitHubIntegration()
        return [
            github_integration.list_repos,
            github_integration.create_issue,
            github_integration.get_issues
        ]
    except Exception as e:
        print(f"GitHub integration failed: {e}")
        return []
