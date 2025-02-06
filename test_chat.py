from maistro.core.agent import MusicAgent

def main():
    agent = MusicAgent("dolla_llama")
    print("\nChat with Dolla Llama (type 'exit' to quit)")
    print("-" * 50)

    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() in ['exit', 'quit']:
            break
            
        response = agent.chat(user_input)
        print(f"\nDolla Llama: {response}")

if __name__ == "__main__":
    main()