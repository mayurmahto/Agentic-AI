from langgraph.graph import StateGraph, END
from langchain_community.chat_models import ChatOllama
import pyodbc
from typing import TypedDict, Optional, List, Literal
from docx import Document
import subprocess
import os
import re
import smtplib
from email.message import EmailMessage

# === Setup LLM ===
llm = ChatOllama(model="llama3.1")

# === Define Agent State ===
class AgentState(TypedDict):
    Application_Name: Optional[str]
    status: Optional[Literal["Bad", "Fair", "Good"]]
    sop_filename: Optional[str]
    sop_steps: Optional[List[str]]
    result: Optional[str]
    next: Optional[str]
    email_subject: Optional[str]
    email_body: Optional[str]
    Application_Name: Optional[str] 

# === Fetch DB Rows ===
def get_all_rows():
    try:
        conn = pyodbc.connect(
            'DRIVER={ODBC Driver 17 for SQL Server};'
            'SERVER=DESKTOP-VMDJII2\\SQLEXPRESS;'
            'DATABASE=app_metrics;'
            'Trusted_Connection=yes;'
        )
        cursor = conn.cursor()
        cursor.execute("SELECT Components, Health, SOP_Name FROM app_heath_metrics")
        return cursor.fetchall()
    except Exception as e:
        print("[DB ERROR] Failed to fetch rows:", e)
        return []

# === Read and Extract Steps from SOP ===
def read_sop(state: AgentState) -> AgentState:
    try:
        file_path = f"./sops_docs/{state['sop_filename']}"
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"SOP file not found: {file_path}")
        doc = Document(file_path)
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())

        prompt = (
            f"The following SOP document contains resolution steps.\n"
            f"Extract all steps from the text provided to be taken:--->{text}"
        )

        response = llm.invoke(prompt)
        steps = response.content.strip().splitlines()
        return {"sop_steps": steps}
    except Exception as e:
        print(f"[ERROR] SOP processing failed: {e}")
        return {"sop_steps": []}

# === Execute Python Scripts ===
def perform_automation(state: AgentState) -> AgentState:
    steps = state.get("sop_steps", [])
    for step in steps:
        if ".py" in step.lower():
            match = re.search(r'([A-Za-z0-9_]+\.py)', step)
            if match:
                script = match.group(1)
                path = os.path.join("./scripts", script)
                try:
                    if os.path.isfile(path):
                        print("\n--- Executing SOP Python Script ---")
                        print(f"-> Running: {script}")
                        subprocess.run(["python", path], check=True)
                        print("\n--- Execution Ended ---")
                    else:
                        print(f"-> [ERROR] Not found: {path}")
                except subprocess.CalledProcessError as e:
                    print(f"-> [ERROR] Failed: {e}")
            else:
                print(f"-> [ERROR] Invalid script step: {step}")
        else:
            print(f"-> [SKIP] Not a script: {step}")
    return {"result": "Automation completed"}

# === LLM-Generated Email Alert ===
def send_email_alert(state: AgentState) -> AgentState:
    try:
        subject = state["email_subject"]
        body = state["email_body"]
        sender = "mahtomayur123@gmail.com"
        receiver = "mahtomayur123@gmail.com"
        password = "nmjc fsef ztam vqrt"
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = receiver
        msg.set_content(body)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender, password)
            smtp.send_message(msg)

        print("[EMAIL] Sent alert successfully.")
        return {"result": "Email sent"}
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        return {"result": "Email failed"}

# === LLM Router + Email Writer ===
def route_with_llm(state: AgentState) -> dict:
    prompt = f"""
    You are an AI system deciding corrective actions based on Health extracted after querying a database.

    Application Name: {state['Application_Name']}
    Status: {state['status']}

    Decide only one of the following action based on the status:
    - If the status is "Bad": return `action: read_sop`
    - If the status is "Fair": return `action: send_email_alert`
    - If the status is "Good": return `action: END`

    If you choose send_email_alert, also return a meaningful email subject and body.

    Reply only in the following exact format:
    if action: <send_email_alert | END>
        subject: <email subject> (only if sending email alert)
        body: <email body> at the end of the Body please add the following lines
        Regards, 
        Agentic AI Team (only if sending email alert)
    """

    response = llm.invoke(prompt).content
    print(f"[LLM RESPONSE]---> {response}\n")

    # Parse response
    action = "END"
    subject = ""
    body_lines = []
    in_body = False

    for line in response.strip().splitlines():
        line = line.strip()
        if line.lower().startswith("action:"):
            action = line.split(":", 1)[1].strip()
            in_body = False
        elif line.lower().startswith("subject:"):
            subject = line.split(":", 1)[1].strip()
            in_body = False
        elif line.lower().startswith("body:"):
            body_line = line.split(":", 1)[1].strip()
            body_lines.append(body_line)
            in_body = True
        elif in_body:
            body_lines.append(line)

    body = "\n".join(body_lines).strip()

    return {
        "next": action,
        "email_subject": subject if action == "send_email_alert" else None,
        "email_body": body if action == "send_email_alert" else None
    }

# === Build LangGraph ===
graph_builder = StateGraph(AgentState)
graph_builder.add_node("route", route_with_llm)
graph_builder.add_node("read_sop", read_sop)
graph_builder.add_node("perform_automation", perform_automation)
graph_builder.add_node("send_email_alert", send_email_alert)

graph_builder.set_entry_point("route")

graph_builder.add_conditional_edges(
    "route",
    lambda state: state["next"],
    {
        "read_sop": "read_sop",
        "send_email_alert": "send_email_alert",
        "END": END,
    }
)

graph_builder.add_edge("read_sop", "perform_automation")
graph_builder.add_edge("perform_automation", END)
graph_builder.add_edge("send_email_alert", END)

graph = graph_builder.compile()

# === Run Agent for All SOPs ===
for Application, status, sop_file in get_all_rows():
    print(f"\n=== When {Application} Status is {status} ===" )
    inputs = {
        "Application_Name": Application,
        "status": status,
        "sop_filename": sop_file
    }
    final_state = graph.invoke(inputs)
    print("Final State:", final_state)
