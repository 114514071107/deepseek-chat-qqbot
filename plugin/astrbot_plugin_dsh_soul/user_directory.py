"""Retired commands never bind identities or write a directory."""
import re
HELP='私聊用户与整个群聊分别管理、分别记忆，无需身份关联。'
def handle(event,scope,root,text,**kwargs):
 if re.fullmatch(r'(关联身份|确认关联|取消关联验证|身份帮助|设置称呼)(?:\s+.*)?',text.strip(),re.S):return HELP
 return None
def onboarding(*args,**kwargs):return None
