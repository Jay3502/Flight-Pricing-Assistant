class ToolLoader:
    def __init__(self, mcp_client, allowed_tags):
        self.mcp = mcp_client
        self.allowed_tags = [tag.lower() for tag in allowed_tags]

    async def load(self):
        result = await self.mcp.list_tools()
        # Note: If result is the ListToolsResult object, we need result.tools
        all_tools = result if isinstance(result, list) else getattr(result, 'tools', [])
        
        llm_tools = []

        print(f"DEBUG: MCP Server provided {len(all_tools)} total tools.")

        for t in all_tools:
            # Let's see what the tool is called and what its tags are
            annotations = getattr(t, "annotations", {})
            tags = annotations.get("tags", []) if isinstance(annotations, dict) else []
            print(f"DEBUG: Found tool '{t.name}' with tags: {tags}")

            # NEW LOGIC: Match if allowed_tags is empty, 
            # OR if a tag matches, OR if the tool name contains our keyword
            should_include = not self.allowed_tags or \
                             any(tag.lower() in [tg.lower() for tg in tags] for tag in self.allowed_tags) or \
                             any(tag.lower() in t.name.lower() for tag in self.allowed_tags)

            if should_include:
                llm_tools.append({
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description or "",
                        "parameters": t.inputSchema,
                    },
                })
        
        return llm_tools