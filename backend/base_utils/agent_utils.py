
from langchain_community.chat_models import ChatOllama
class AgentUtils():
    def __init__(self):
        self.llm = ChatOllama(
            model="deepseek-r1:1.5b",
            base_url="http://localhost:11434"  # 注意这里不需要 /v1
        )

    def run(self,content):
        result=self.llm.invoke(content)
        print(result)


if __name__=="__main__":
    agent_utils=AgentUtils()
    content="帮我提取这个图片中表格的内容，/Users/admin/Desktop/ZnYan/auto_test_utils/QQ20260317-153421.png"
    agent_utils.run(content)