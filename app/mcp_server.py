from mcp.server import FastMCP

# Create a FastMCP server
mcp = FastMCP("Resume Gap Analyzer Server")

@mcp.tool()
def search_courses(skill: str) -> str:
    """Searches for online courses or learning resources to learn a specific skill."""
    skill_lower = skill.lower()
    if "python" in skill_lower:
        return "1. Python for Everybody (Coursera)\n2. Complete Python Bootcamp (Udemy)\n3. Google IT Automation with Python Professional Certificate (Coursera)"
    elif "cloud" in skill_lower or "aws" in skill_lower or "gcp" in skill_lower:
        return "1. Google Cloud Digital Leader Training (Coursera)\n2. AWS Certified Solutions Architect Associate (Udemy)\n3. Google Associate Cloud Engineer Certificate"
    elif "machine learning" in skill_lower or "ml" in skill_lower or "ai" in skill_lower:
        return "1. Machine Learning Specialization by Andrew Ng (Coursera)\n2. Deep Learning Specialization (Coursera)\n3. Introduction to Generative AI (Google Cloud)"
    else:
        return f"1. {skill} Fundamental Course (LinkedIn Learning)\n2. Mastering {skill} (Udemy)\n3. Advanced {skill} Techniques (Pluralsight)"

@mcp.tool()
def fetch_job_trends(skill: str) -> str:
    """Fetches market demand and trends for specific skills or roles."""
    skill_lower = skill.lower()
    if "python" in skill_lower or "javascript" in skill_lower:
        return f"Skill '{skill}' has extremely high market demand. Featured in 45% of software engineering job postings. Salary premium: +12%."
    elif "ai" in skill_lower or "machine learning" in skill_lower or "ml" in skill_lower:
        return f"Skill '{skill}' demand is growing exponentially (+150% year-over-year). Critical for modern AI/ML engineer roles."
    else:
        return f"Skill '{skill}' has steady demand. Featured in approximately 15% of relevant job postings."

@mcp.tool()
def verify_resume_format(resume_text: str) -> str:
    """Checks the format, layout, and structure of a resume for readability and ATS friendliness."""
    score = 100
    feedbacks = []
    
    word_count = len(resume_text.split())
    if word_count < 100:
        score -= 30
        feedbacks.append("Resume is too short. Include more details on roles, achievements, and technical stack.")
    elif word_count > 1200:
        score -= 10
        feedbacks.append("Resume is too long (over 1200 words). Keep it concise and limited to 2 pages.")
        
    if "phone" in resume_text.lower() or "[phone]" in resume_text.lower() or "your-phone" in resume_text.lower():
        score -= 15
        feedbacks.append("Found placeholders in the contact details section. Make sure to replace them with real information.")
        
    headers = ["experience", "education", "skills", "projects"]
    missing_headers = [h for h in headers if h not in resume_text.lower()]
    if missing_headers:
        score -= len(missing_headers) * 10
        feedbacks.append(f"Missing recommended sections: {', '.join(missing_headers)}")
        
    if not feedbacks:
        feedbacks.append("Resume layout and sections look clean and ATS-friendly.")
        
    return f"Verification Score: {score}/100\nFeedback:\n" + "\n".join([f"- {f}" for f in feedbacks])

if __name__ == "__main__":
    mcp.run()
