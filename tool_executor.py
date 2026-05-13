import json

class ToolExecutor:
    def __init__(self, mcp_client):
        self.mcp = mcp_client

    async def execute(self, tool_plan):
        results = []
        for call in tool_plan:
            tool_name = call.get("name") 
            tool_args = call.get("args", {})
            
            print(f"Executing MCP Tool: {tool_name}")
            
            try:
                # 1. Get raw result
                raw_result = await self.mcp.call_tool(tool_name, tool_args)
                
                # 2. Extract and parse text content
                for content_block in getattr(raw_result, 'content', []):
                    if hasattr(content_block, 'text'):
                        try:
                            # Convert the JSON string into a Python dict/list
                            parsed_data = json.loads(content_block.text)
                            results.append({
                                "source": tool_name,
                                "data": parsed_data
                            })
                        except json.JSONDecodeError:
                            # Fallback if it's just plain text
                            results.append({"source": tool_name, "data": content_block.text})
                
            except Exception as e:
                print(f"Error calling {tool_name}: {e}")
                
        return results