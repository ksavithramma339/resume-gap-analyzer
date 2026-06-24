import datetime
import os
import re
import sys
from typing import List, Optional, Any

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.workflow import Workflow, START, node
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.adk.tools import AgentTool
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from google.genai import types
from pydantic import BaseModel, Field

from .config import config

# --- 1. Pydantic Models for Structured Input/Output ---

class JobAnalysisRequest(BaseModel):
    resume_text: str = Field(description="The plain text of the resume to be analyzed.")
    job_description: str = Field(description="The job description to compare the resume against.")

class ResumeAnalysis(BaseModel):
    skills: List[str] = Field(description="Extracted skills from the resume.")
    experience_years: float = Field(description="Estimated years of professional experience.")
    key_experience_summary: str = Field(description="Brief summary of key roles and achievements.")

class GapAnalysis(BaseModel):
    matching_skills: List[str] = Field(description="Skills that match the job description.")
    missing_skills: List[str] = Field(description="Required or preferred skills that are missing in the resume.")
    match_score: int = Field(description="Overall match percentage from 0 to 100.")
    recommendations: List[str] = Field(description="Specific actionable recommendations to improve the resume or skills.")

# --- 2. MCP Toolset Setup ---

mcp_server_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "mcp_server.py"))

gap_analyzer_mcp = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=[mcp_server_path],
        )
    ),
    tool_filter=["verify_resume_format"],
)

gap_enhancer_mcp = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=[mcp_server_path],
        )
    ),
    tool_filter=["search_courses", "fetch_job_trends"],
)

# --- 3. Specialized LLM Sub-agents ---

resume_analyzer = LlmAgent(
    name="resume_analyzer",
    model=config.model,
    instruction="""You are the Resume Analyzer specialist.
    Analyze the candidate's resume and extract their skills, years of experience, and key experience summary.
    Return structured output matching the ResumeAnalysis schema.
    """,
    description="Analyzes a resume and extracts skills and experience.",
    output_schema=ResumeAnalysis,
    output_key="resume_analysis"
)

gap_analyzer = LlmAgent(
    name="gap_analyzer",
    model=config.model,
    instruction="""You are the Gap Analyzer specialist.
    Compare the resume analysis details against the job description.
    First, use the `verify_resume_format` tool to verify the structure, formatting, and ATS friendliness of the original resume.
    Identify matching skills, missing/weak skills, a match score, and recommendations.
    Return structured output matching the GapAnalysis schema.
    """,
    description="Compares resume details against a job description to identify gaps.",
    output_schema=GapAnalysis,
    output_key="gap_analysis",
    tools=[gap_analyzer_mcp],
)

# --- 4. Main Orchestrator Agent ---

orchestrator = LlmAgent(
    name="orchestrator",
    model=config.model,
    instruction="""You are the Resume Analyzer Orchestrator. 
    You will receive a candidate's resume and a job description to compare it against.
    
    Your goal is to coordinate the analysis:
    1. First, call `resume_analyzer` to analyze the candidate's resume.
    2. Next, call `gap_analyzer` with the resume analysis results, the original resume, and the job description to identify formatting issues and skill gaps.
    3. Output the combined findings as a clear summary report.
    """,
    tools=[AgentTool(resume_analyzer), AgentTool(gap_analyzer)],
)


# --- 5. Gap Enhancer Agent ---

gap_enhancer = LlmAgent(
    name="gap_enhancer",
    model=config.model,
    instruction="""You are the Gap Enhancer.
    Review the missing skills identified in the gap analysis: {gap_analysis}
    Use `search_courses` and `fetch_job_trends` tools to find specific courses and market demand trends for these missing skills.
    Provide 3 high-quality learning resources, courses, or certification paths to fill these gaps.
    """,
    output_key="enhanced_output",
    tools=[gap_enhancer_mcp],
)


# --- 5. Workflow Node Functions ---

def security_checkpoint(ctx: Context, node_input: JobAnalysisRequest) -> Event:
    # 1. PII Scrubbing
    ssn_pattern = r'\b\d{3}-\d{2}-\d{4}\b'
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    phone_pattern = r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'
    
    scrubbed_resume = re.sub(ssn_pattern, "[REDACTED SSN]", node_input.resume_text)
    scrubbed_resume = re.sub(email_pattern, "[REDACTED EMAIL]", scrubbed_resume)
    scrubbed_resume = re.sub(phone_pattern, "[REDACTED PHONE]", scrubbed_resume)
    
    scrubbed_jd = re.sub(ssn_pattern, "[REDACTED SSN]", node_input.job_description)
    scrubbed_jd = re.sub(email_pattern, "[REDACTED EMAIL]", scrubbed_jd)
    scrubbed_jd = re.sub(phone_pattern, "[REDACTED PHONE]", scrubbed_jd)
    
    # 2. Prompt Injection Detection
    injection_keywords = ["ignore previous instructions", "system prompt", "bypass guardrails", "override rules", "you are now a chatgpt"]
    has_injection = False
    combined_text = (scrubbed_resume + " " + scrubbed_jd).lower()
    for kw in injection_keywords:
        if kw in combined_text:
            has_injection = True
            break
            
    # 3. Domain-specific rule: Validate that the document contains basic resume structure keywords
    resume_headings = ["education", "experience", "work", "skills", "projects", "employment", "history", "career"]
    matched_headings = [h for h in resume_headings if h in scrubbed_resume.lower()]
    is_valid_resume = len(matched_headings) >= 2
    
    # Save scrubbed input in state
    ctx.state["scrubbed_resume"] = scrubbed_resume
    ctx.state["scrubbed_jd"] = scrubbed_jd
    
    # Audit log
    audit_log = {
        "timestamp": datetime.datetime.now().isoformat(),
        "pii_detected": scrubbed_resume != node_input.resume_text or scrubbed_jd != node_input.job_description,
        "injection_detected": has_injection,
        "valid_resume_format": is_valid_resume,
        "severity": "CRITICAL" if has_injection else ("WARNING" if not is_valid_resume or scrubbed_resume != node_input.resume_text else "INFO")
    }
    ctx.state["security_log"] = audit_log
    
    if has_injection:
        return Event(output="Access Denied: Prompt injection detected.", route="SECURITY_EVENT")
    elif not is_valid_resume:
        return Event(output="Access Denied: Document does not appear to be a valid resume (missing standard sections like education, experience, or skills).", route="SECURITY_EVENT")
    else:
        # Pass the scrubbed request forward as a dict string for the LlmAgent
        prompt_input = f"Resume:\n{scrubbed_resume}\n\nJob Description:\n{scrubbed_jd}"
        return Event(output=prompt_input, route="PROCEED")


def security_event_handler(ctx: Context, node_input: str) -> Event:
    msg = f"⚠️ Security violation! Access denied: {node_input}\nAudit Log: {ctx.state.get('security_log')}"
    yield Event(content=types.Content(role='model', parts=[types.Part.from_text(text=msg)]))
    yield Event(output=msg)


async def ask_learning_paths(ctx: Context, node_input: Any) -> Event:
    # Save the orchestrator's output into state
    ctx.state["orchestrator_output"] = str(node_input)
    
    if not ctx.resume_inputs:
        yield RequestInput(
            interrupt_id="suggest_courses",
            message="Would you like me to fetch learning resources and courses to help you fill the identified skill gaps? (yes/no)"
        )
        return
        
    user_choice = ctx.resume_inputs.get("suggest_courses", "no")
    ctx.state["suggest_courses"] = user_choice
    
    if user_choice.lower().strip() in ["yes", "y"]:
        yield Event(output="Recommend course suggestions.", route="yes")
    else:
        yield Event(output="No recommendations requested.", route="no")


def final_report(ctx: Context, node_input: Any) -> Event:
    orchestrator_output = ctx.state.get("orchestrator_output", "No initial analysis found.")
    enhanced_output = ctx.state.get("enhanced_output", "No course recommendations requested.")
    
    report_text = f"""
# 📋 Resume Gap Analysis Report

## 🔍 Initial Evaluation
{orchestrator_output}

## 📚 Learning & Development Recommendations
{enhanced_output}

---
*Security Audit Log: {ctx.state.get('security_log')}*
"""
    yield Event(content=types.Content(role='model', parts=[types.Part.from_text(text=report_text)]))
    yield Event(output=report_text)


# --- 6. Workflow Definition ---

edges = [
    (START, security_checkpoint),
    (security_checkpoint, {"SECURITY_EVENT": security_event_handler, "PROCEED": orchestrator}),
    (orchestrator, ask_learning_paths),
    (ask_learning_paths, {"yes": gap_enhancer, "no": final_report}),
    (gap_enhancer, final_report),
]

root_agent = Workflow(
    name="resume_gap_analyzer",
    input_schema=JobAnalysisRequest,
    edges=edges,
)

app = App(
    root_agent=root_agent,
    name="app",
)
