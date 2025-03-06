from typing import Optional
from anthropic import Anthropic
from maistro.core.memory.manager import MemoryManager
from maistro.core.llm.messages import MessageHistory
from .prompt import create_chat_prompt

def chat_session(agent, message_history: Optional[MessageHistory] = None):
    """
    Start an interactive chat session with the agent
    
    Args:
        agent: The MusicAgent instance
        message_history: Optional existing message history to continue a conversation
    """
    # Create new message history if not provided
    if message_history is None:
        chat_prompt, _ = create_chat_prompt(
            config=agent.config,
            artist_name=agent.artist_name,
            client=agent.client
        )
        message_history = MessageHistory(chat_prompt)
    
    print(f"\nChatting with {agent.artist_name} (type 'exit' to quit)")
    print("-" * 50)

    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() in ['exit', 'quit']:
            break

        # Get a single response and display it
        response = chat_response(
            user_input, 
            message_history, 
            agent.memory, 
            agent.client
        )
        
        print(f"\n{agent.artist_name}: {response}")

def chat_response(
    message: str, 
    message_history: MessageHistory, 
    memory_manager: MemoryManager, 
    llm_client: Anthropic
) -> str:
    """
    Get a single chat response
    
    Args:
        message: User message text
        message_history: Message history for the conversation
        memory_manager: Memory manager for retrieving context
        llm_client: Anthropic client for API calls
        
    Returns:
        Response text from the LLM
    """
    # Get relevant memories
    memory_context, results = memory_manager.get_relevant_context(message)
    
    # Log retrieved memory for debugging
    if results:
        print("\nRetrieved Chunks (in order of relevance):")
        for i, result in enumerate(results, 1):
            print(f"\n{i}. Score: {result.similarity_score:.3f}")
            print(f"Document: {result.memory.metadata.get('source', 'Unknown')}")
            print(f"Category: {result.memory.category}")
            print(f"Content Preview: {result.memory.content[:200]}...")
    else:
        print("Memory context: <none>")
    
    # Add user message with context
    message_history.add_user_message(message, memory_context)

    # Get messages and print the first one for debugging
    messages = message_history.get_messages()

    print("\n========== ALL MESSAGES SENT TO LLM ==========")
    for idx, msg in enumerate(messages):
        print(f"Message {idx} ({msg['role']}):")
        print(msg['content'])
        print("---------------------------------------------")
    print("===============================================\n")
    
    # Get response from LLM
    messages = message_history.get_messages()
    response = llm_client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1000,
        messages=messages
    )
    
    # Extract response text
    response_text = response.content[0].text
    
    # Add assistant response to message history
    message_history.add_assistant_message(response_text)
    
    return response_text