from typing import List, Dict, Optional

class MessageHistory:
    """Manages message history for LLM interactions"""
    
    def __init__(self, persona_prompt: str):
        """
        Initialize message history with persona prompt
        
        Args:
            persona_prompt: String containing the persona instructions
        """
        # Start with the persona prompt as the first user message
        self.messages = [{
            "role": "user",
            "content": persona_prompt
        }]
        
        # Track if we've received the first response
        self.initialized = False
        
        # Maximum history to maintain (to avoid token limits)
        self.max_pairs = 12  # Keep ~12 conversation pairs (24 messages)

    def add_user_message(self, user_input: str, memory_context: Optional[str] = None) -> Dict:
        """
        Add a user message, optionally including memory context
        
        Args:
            user_input: The user's message
            memory_context: Optional memory context to include
            
        Returns:
            The user message dictionary that was added
        """
        # Combine memory context with user input if provided
        content = user_input
        if memory_context:
            content = f"If relevant to the conversation, feel free to naturally draw upon the following excerpts from your memory and knowledge: \n\n{memory_context}\n\n{user_input}"
            
        # Create and add the user message
        user_message = {"role": "user", "content": content}
        self.messages.append(user_message)
        
        return user_message
    
    def add_assistant_message(self, response_text: str) -> None:
        """
        Add an assistant response to the message history
        
        Args:
            response_text: The text response from the assistant
        """
        self.messages.append({"role": "assistant", "content": response_text})
        self.initialized = True
        
        # Prune history if needed
        self._prune_history()
        
    def get_messages(self) -> List[Dict]:
        """
        Return the current message history suitable for LLM API calls
        
        Returns:
            List of message dictionaries
        """
        # Always return the full message history including the persona prompt
        # This ensures the LLM maintains the character throughout the conversation
        return self.messages
    
    def clear_history(self, preserve_persona: bool = True) -> None:
        """
        Clear the message history
        
        Args:
            preserve_persona: Whether to keep the initial persona message
        """
        if preserve_persona and len(self.messages) > 0:
            # Keep just the first message (persona details)
            first_message = self.messages[0]
            self.messages = [first_message]
        else:
            self.messages = []
            
        self.initialized = False
    
    def _prune_history(self) -> None:
        """Reduce message history if it exceeds the maximum length"""
        # Keep the first message (persona prompt) and most recent messages
        if len(self.messages) > (self.max_pairs * 2 + 1):
            # Keep the first message and the most recent max_pairs*2 messages
            self.messages = [self.messages[0]] + self.messages[-(self.max_pairs * 2):]
    
    def __len__(self) -> int:
        """Return the number of messages in the history"""
        return len(self.messages)