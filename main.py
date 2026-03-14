import nest_asyncio
import os
import sys
import asyncio
import logging
import glob
import importlib
from typing import List, Dict, Any, Sequence, TypedDict
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import httpx

# Allow nested event loop on Windows
nest_asyncio.apply()

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Project root (CWD-independent paths)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Import LangChain components
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langchain_experimental.tools.python.tool import PythonREPLTool
from langchain_community.agent_toolkits import FileManagementToolkit
from typing import Annotated
import operator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI()


@app.get("/health")
def health():
    """Health check for load balancers and monitoring."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness check (e.g. after bot and LLM are configured)."""
    return {"status": "ready"}

# ============== STATE DEFINITION ==============
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]

# ============== GITHUB INTEGRATION ==============
class GitHubIntegration:
    def __init__(self):
        try:
            from github import Github
            github_token = os.getenv("GITHUB_TOKEN")
            if not github_token:
                raise ValueError("GITHUB_TOKEN not found in environment variables")
            self.github = Github(github_token)
            self.enabled = True
        except ImportError:
            logger.warning("GitHub integration disabled - PyGithub not installed")
            self.enabled = False
        except Exception as e:
            logger.warning(f"GitHub integration disabled: {e}")
            self.enabled = False
            
    def get_tools(self):
        if not self.enabled:
            return []
        
        @tool
        def list_repos() -> str:
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
        def create_issue(repo_name: str, title: str, body: str) -> str:
            """Create an issue in a repository"""
            try:
                user = self.github.get_user()
                repo = user.get_repo(repo_name)
                issue = repo.create_issue(title=title, body=body)
                return f"Issue created: {issue.html_url}"
            except Exception as e:
                return f"Error creating issue: {str(e)}"
                
        @tool
        def get_issues(repo_name: str) -> str:
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
                
        return [list_repos, create_issue, get_issues]

# ============== EMAIL INTEGRATION ==============
class EmailIntegration:
    def __init__(self):
        try:
            self.smtp_server = os.getenv("SMTP_SERVER", "smtp-mail.outlook.com")
            self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
            self.email = os.getenv("EMAIL_ADDRESS")
            self.password = os.getenv("EMAIL_PASSWORD")
            
            if not all([self.email, self.password]):
                raise ValueError("Email credentials not found in environment variables")
            self.enabled = True
        except Exception as e:
            logger.warning(f"Email integration disabled: {e}")
            self.enabled = False
            
    def get_tools(self):
        if not self.enabled:
            return []
        
        @tool
        def send_email(to: str, subject: str, body: str) -> str:
            """Send an email"""
            try:
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart
                import smtplib
                
                msg = MIMEMultipart()
                msg['From'] = self.email
                msg['To'] = to
                msg['Subject'] = subject
                
                msg.attach(MIMEText(body, 'plain'))
                
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                server.starttls()
                server.login(self.email, self.password)
                server.send_message(msg)
                server.quit()
                
                return f"Email sent to {to}"
            except Exception as e:
                return f"Error sending email: {str(e)}"
                
        return [send_email]

# ============== WEBHOOK SETUP ==============
async def set_webhook(bot_token: str, webhook_url: str):
    """Set the webhook URL for the Telegram bot"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.telegram.org/bot{bot_token}/setWebhook",
                json={"url": webhook_url}
            )
            result = response.json()
            if result.get("ok"):
                logger.info("Webhook set successfully")
                return True
            else:
                logger.error(f"Failed to set webhook: {result}")
                return False
    except Exception as e:
        logger.error(f"Error setting webhook: {e}")
        return False

@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Handle incoming Telegram webhook requests."""
    try:
        update_data = await request.json()
        update = Update.de_json(update_data)
        await application.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        logger.error("Error processing webhook: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

# ============== LLM CHOICE ==============
def get_llm():
    """Initialize and return the LLM instance (cloud Ollama)."""
    base_url = os.getenv("OLLAMA_API_BASE", "https://api.ollama.com/v1")
    api_key = os.getenv("OLLAMA_API_KEY")
    model_name = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:14b-instruct-q6_K")  # or whatever variant they have
    
    if not api_key:
        raise ValueError("OLLAMA_API_KEY not set in environment variables")
    
    logger.info(f"Using Ollama cloud model: {model_name} @ {base_url}")
    
    return ChatOllama(
        model=model_name,
        base_url=base_url,
        api_key=api_key,
        temperature=0.3,
        # optional: add timeout/streaming tweaks if needed
        request_timeout=120.0,
    )


# Initialize LLM at module load (fail fast if config missing)
llm = get_llm()

# ============== TOOL SETUP ==============
def get_all_tools():
    """Get all available tools for the agent"""
    # DuckDuckGo is provided by skills/web_search.py; avoid duplicate
    tools = [
        PythonREPLTool(),
    ]
    
    # Load file management tools
    file_tools = FileManagementToolkit(
        root_dir=PROJECT_ROOT,
        selected_tools=["read_file", "write_file", "list_directory"]
    ).get_tools()
    tools.extend(file_tools)
    
    # Load GitHub tools
    github_integration = GitHubIntegration()
    tools.extend(github_integration.get_tools())
    
    # Load email tools
    email_integration = EmailIntegration()
    tools.extend(email_integration.get_tools())
    
    # Load custom skills
    def load_custom_skills(tools_list: List) -> None:
        """Dynamically load custom skills from the 'skills' directory."""
        skills_glob = os.path.join(PROJECT_ROOT, "skills", "*.py")
        for skill_path in glob.glob(skills_glob):
            try:
                # Derive module name: e.g. .../skills/web_search.py -> skills.web_search
                rel = os.path.relpath(skill_path, PROJECT_ROOT)
                module_path = rel.replace("\\", "/").replace(".py", "").replace("/", ".")
                module = importlib.import_module(module_path)
                if hasattr(module, "get_tools"):
                    tools_list.extend(module.get_tools())
                    logger.info(f"Loaded skill: {skill_path}")
            except Exception as e:
                logger.warning(f"Failed to load skill: {skill_path} - {str(e)}")
    
    load_custom_skills(tools)
    return tools

# ============== AGENT WORKFLOW ==============
def create_agent_workflow():
    """Create the LangGraph agent workflow"""
    tools = get_all_tools()
    llm_with_tools = llm.bind_tools(tools)
    
    # Define nodes
    def call_model(state: AgentState):
        """Call the model with the current state"""
        response = llm_with_tools.invoke(state["messages"])
        return {"messages": [response]}
    
    def call_tools(state: AgentState):
        """Execute tools based on model response"""
        messages = state["messages"]
        last_message = messages[-1]
        
        if not hasattr(last_message, 'tool_calls'):
            return {"messages": []}
        
        tool_responses = []
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            
            # Find matching tool
            matching_tool = None
            for t in tools:
                if hasattr(t, 'name') and t.name == tool_name:
                    matching_tool = t
                    break
                elif hasattr(t, '__name__') and t.__name__ == tool_name:
                    matching_tool = t
                    break
            
            if matching_tool:
                try:
                    result = matching_tool.invoke(tool_args)
                    tool_responses.append(
                        AIMessage(
                            content=str(result),
                            tool_call_id=tool_call["id"]
                        )
                    )
                except Exception as e:
                    tool_responses.append(
                        AIMessage(
                            content=f"Error executing {tool_name}: {str(e)}",
                            tool_call_id=tool_call["id"]
                        )
                    )
        
        return {"messages": tool_responses}
    
    def should_continue(state: AgentState):
        """Determine if we should continue or end"""
        messages = state["messages"]
        if not messages:
            return "end"
        last_message = messages[-1]
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "tools"
        return "end"
    
    # Create workflow
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", call_tools)
    
    # Add edges
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "end": END
        }
    )
    workflow.add_edge("tools", "agent")
    workflow.add_edge(START, "agent")
    
    # Compile with checkpointing
    memory_path = os.path.join(PROJECT_ROOT, "droxclaw_memory.db")
    memory = SqliteSaver.from_conn_string(memory_path)
    return workflow.compile(checkpointer=memory)

# ============== TELEGRAM BOT HANDLERS ==============
def _get_agent():
    """Return the shared compiled agent (lazy init)."""
    global _agent
    if _agent is None:
        _agent = create_agent_workflow()
    return _agent


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages from users."""
    user_id = str(update.effective_user.id)
    agent = _get_agent()

    # Process message through agent (per-user memory via thread_id)
    try:
        config = {"configurable": {"thread_id": user_id}}
        response = await agent.ainvoke({
            "messages": [HumanMessage(content=update.message.text)]
        }, config=config)
        
        # Extract final response (last message may have no content if tool-only)
        last_msg = response["messages"][-1]
        final_message = getattr(last_msg, "content", None) or ""
        await update.message.reply_text(str(final_message) if final_message else "Done.")
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        await update.message.reply_text("Sorry, I encountered an error processing your request.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when the command /start is issued."""
    await update.message.reply_text("DroxClaw online. What do you want automated tonight?")

# ============== ERROR HANDLER ==============
async def error_handler(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors caused by updates."""
    logger.error(
        "Exception while handling an update: %s",
        context.error,
        exc_info=True,
    )

# ============== PROACTIVE HEARTBEAT JOB ==============
async def heartbeat(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Periodic task that sends a status update to the admin."""
    job = context.job
    chat_id = job.data.get('chat_id')
    if chat_id:
        await context.bot.send_message(
            chat_id=chat_id,
            text="DroxClaw heartbeat — still alive and watching"
        )
    else:
        logger.warning("Heartbeat triggered but no chat_id provided.")

# Global application references
application = None
# Single shared agent; checkpointer isolates state by thread_id per user
_agent = None

# ============== MAIN ENTRY POINT ==============
async def main() -> None:
    """Main entry point to run the bot."""
    global application
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables")

    # Create application
    application = Application.builder().token(token).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Add error handler
    application.add_error_handler(error_handler)

    # Schedule heartbeat using JobQueue
    chat_id_str = os.getenv("ADMIN_CHAT_ID")
    if chat_id_str:
        try:
            chat_id = int(chat_id_str)
            application.job_queue.run_repeating(
                heartbeat,
                interval=300,       # Every 5 minutes
                first=10,           # First run after 10 seconds
                data={'chat_id': chat_id},
                name="heartbeat"
            )
            logger.info("Heartbeat scheduled via JobQueue.")
        except ValueError:
            logger.error("ADMIN_CHAT_ID must be a valid integer.")
    else:
        logger.warning("No ADMIN_CHAT_ID set — heartbeat disabled.")

    # Initialize the application
    await application.initialize()
    
    # Set webhook
    webhook_url = os.getenv("WEBHOOK_URL")
    if webhook_url:
        success = await set_webhook(token, webhook_url)
        if success:
            logger.info("DroxClaw webhook mode enabled")
            # Start FastAPI server
            config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
            server = uvicorn.Server(config)
            await server.serve()
        else:
            logger.error("Failed to set webhook, falling back to polling")
            await application.run_polling()
    else:
        logger.info("DroxClaw polling mode enabled")
        await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
