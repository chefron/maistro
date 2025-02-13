from maistro.core.memory.manager import MemoryManager

def main():
    memory = MemoryManager("dolla-llama")
    
    # Debug checks
    print("\nCategory Stats:")
    print(memory.get_category_stats('songs'))
    
    print("\nDirect Collection Access:")
    collection = memory.store.collections.get('songs')
    if collection:
        print(collection.get())
    
    print("\nDB Path:")
    print(memory.store.db_path)

if __name__ == "__main__":
    main()