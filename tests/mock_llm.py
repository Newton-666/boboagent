"""Mock LLM caller for testing — returns canned responses instantly, no API key needed."""


class MockLLMCaller:
    """Returns pre-defined responses in sequence, no network calls.

    Usage:
        caller = MockLLMCaller([
            {"choices": [{"message": {"content": "Hello!"}}]},
            {"choices": [{"message": {"content": "", "tool_calls": [
                {"function": {"name": "get_current_time", "arguments": "{}"}}
            ]}}]},
        ])
        result = caller([{"role": "user", "content": "hi"}])
    """

    def __init__(self, responses: list):
        self.responses = list(responses)
        self.call_count = 0

    def __call__(self, messages, use_tools=True, stream_callback=None,
                 retry_callback=None, tools_override=None):
        """Matches the real llm_caller interface."""
        idx = self.call_count
        self.call_count += 1

        if stream_callback:
            # Simulate streaming: emit the content char by char
            for resp in self.responses:
                if idx < len(self.responses):
                    content = self.responses[idx].get("choices", [{}])[0] \
                        .get("message", {}).get("content", "")
                    for char in content:
                        stream_callback(char)
                break

        if idx >= len(self.responses):
            return {"choices": [{"message": {"content": ""}}]}

        result = self.responses[idx]
        # Simulate a small delay for realism in tests
        import time
        time.sleep(0.01)
        return result

    def add_response(self, response: dict):
        """Add a response to the end of the queue."""
        self.responses.append(response)


def create_mock_caller(responses: list = None) -> MockLLMCaller:
    """Factory function that matches create_llm_caller's style."""
    return MockLLMCaller(responses or [{"choices": [{"message": {"content": ""}}]}])


# Commonly used response templates
def text_response(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


def tool_response(tool_name: str, args: dict = None) -> dict:
    return {"choices": [{"message": {
        "content": "",
        "tool_calls": [{
            "function": {"name": tool_name, "arguments": str(args or {})}
        }]
    }}]}
