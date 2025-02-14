from pathlib import Path
import logging
import os
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory

from maistro.core.agent import MusicAgent
from maistro.core.memory import MemoryManager

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class Command:
    """Represents a CLI command"""
    name: str
    description: str
    tips: List[str]
    handler: Callable
    aliases: List[str] = None

    def __post_init__(self):
        if self.aliases is None:
            self.aliases = []

class MaistroCLI:
    def __init__(self):
        self.agent = None

        # Create config directory
        self.config_dir = Path.home() / '.maistro'
        self.config_dir.mkdir(exist_ok=True)

        # Initialize commands and prompt toolkit
        self._initialize_commands()
        self._setup_prompt_toolkit()

    def exit(self, input_list: List[str]) -> None:
        """Exit the CLI"""
        logger.info("\nGoodbye! 👋")
        import sys
        sys.exit(0)

    def _initialize_commands(self) -> None:
        """Initialize CLI commands"""
        self.commands: Dict[str, Command] = {}

        # Agent commands
        self._register_command(
            Command(
                name="load-artist",
                description="Load an artist",
                tips=["Format: load-artist {artist name}",
                      "Use 'list-artists' to see available artists"],
                handler=self.load_agent,
                aliases=['load']
            )
        )

        self._register_command(
            Command(
                name="list-artists",
                description="List all available artists",
                tips=["Artists are stored in the artists directory"],
                handler=self.list_agents,
                aliases=['agents', 'ls-agents']
            )
        )

        self._register_command(
            Command(
                name="chat",
                description="Chat with the artist",
                tips="Use 'exit' or 'quit' to end the chat session",
                handler=self.start_chat,
                aliases=['talk']
            )
        )

        # Memory commands
        self._register_command(
            Command(
                name="memory-upload",
                description="Upload documents to artist's memory",
                tips=["Format: memory-upload {category} file1 [file2...]",
                      "Example categories: songs, feedback, analytics"],
                handler=self.memory_upload,
                aliases=['upload-memory']
            )
        )

        self._register_command(
            Command(
                name="memory-list",
                description="List memory categories or contents",
                tips=["Format: memory-list [category]",
                      "Without category: shows all categories",
                      "With category: shows documents in category"],
                handler=self.memory_list,
                aliases=['list-memories']
            )
        )

        self._register_command(
            Command(
                name="memory-search",
                description="Search artist's memories",
                tips=["Format: memory-search 'query' [category]",
                      "Searches all categories if none specified"],
                handler=self.memory_search,
                aliases=['search-memory']
            )
        )

        self._register_command(
            Command(
                name="memory-wipe",
                description="Delete memories",
                tips=["Format: memory-wipe [category] [filename]",
                      "No arguments: wipes all memories",
                      "Category only: wipes category",
                      "Both: wipes specific document"],
                handler=self.memory_wipe,
                aliases=['wipe-memory']
            )
        )

        # Utility commands
        self._register_command(
            Command(
                name="help",
                description="Show command help",
                tips=["Use 'help {command}' for specific command help"],
                handler=self.help,
                aliases=['?']
            )
        )

        self._register_command(
            Command(
                name="exit",
                description="Exit the CLI",
                tips=["You can also use Ctrl+D"],
                handler=self.exit,
                aliases=['quit']
            )
        )

    def _setup_prompt_toolkit(self) -> None:
        """Configure prompt toolkit components"""
        self.style = Style.from_dict({
            'prompt': 'ansicyan bold',
            'command': 'ansigreen',
            'error': 'ansired bold',
            'success': 'ansigreen bold',
            'warning': 'ansiyellow',
        })

        history_file = self.config_dir / 'history.txt'

        self.completer = WordCompleter(
            list(self.commands.keys()),
            ignore_case=True,
            sentence=True
        )

        self.session = PromptSession(
            completer=self.completer,
            style=self.style,
            history=FileHistory(str(history_file))
        )

    def _register_command(self, command: Command) -> None:
        """Register a command and its aliases"""
        self.commands[command.name] = command
        for alias in command.aliases:
            self.commands[alias] = command

    def _get_prompt_message(self) -> HTML:
        """Generate the prompt message"""
        artist_status = f"({self.agent.artist_name})" if self.agent else "(no artist)"
        return HTML(f'<prompt>Maistro</prompt> {artist_status} > ')
    
    def _handle_command(self, input_string: str) -> None:
        """Parse and handle a command input"""
        input_list = input_string.split()
        if not input_list:
            return
        
        command_string = input_list[0].lower()
        command = self.commands.get(command_string)

        if command:
            try:
                command.handler(input_list)
            except Exception as e:
                logger.error(f"Error handling command: {e}")
        else:
            self._handle_unknown_command(command_string)

    def _handle_unknown_command(self, command:str) -> None:
        """Handle unknown commands with suggestions"""
        logger.warning(f"Unknown command: '{command}'")
        suggestions = self._get_command_suggestions(command)
        if suggestions:
            logger.info("Did you mean:")
            for suggestion in suggestions:
                logger.info(f"  - {suggestion}")
        logger.info("Use 'help' for available commands")

    def _get_command_suggestions(self, command: str, max_suggestions: int = 3) -> List[str]:
        """Get similar command suggestions"""
        from difflib import get_close_matches
        return get_close_matches(command, self.commands.keys(), n=max_suggestions, cutoff=0.6)
    
    def help(self, input_list: List[str]) -> None:
        """Show help information"""
        if len(input_list) > 1:
            command = self.commands.get(input_list[1])
            if command:
                logger.info(f"\nHelp for '{command.name}':")
                logger.info(f"Description: {command.description}")
                if command.aliases:
                    logger.info(f"Aliases: {', '.join(command.aliases)}")
                if command.tips:
                    logger.info("\nTips:")
                    for tip in command.tips:
                        logger.info(f"  - {tip}")
            else:
                logger.warning(f"Unknown command: '{input_list[1]}'")
        else:
            logger.info("\nAvailable Commands:")
            for cmd_name, cmd in sorted(self.commands.items()):
                if cmd_name == cmd.name:  # Show only main commands, not aliases
                    logger.info(f"  {cmd.name:<15} - {cmd.description}")
    
    def load_agent(self, input_list: List[str]) -> None:
        """Load an artist agent"""
        if len(input_list) < 2:
            logger.info("Please specify an artist name")
            logger.info("Format: load-artist {artist_name}")
            return

        artist_name = input_list[1]
        try:
            self.agent = MusicAgent(artist_name)
            logger.info(f"✅ Loaded artist agent: {artist_name}")
        except Exception as e:
            logger.error(f"Error loading artist: {e}")

    def list_agents(self, input_list: List[str]) -> None:
        """List available artist agents"""
        artists_dir = Path(__file__).parent.parent / "artists"
        if not artists_dir.exists():
            logger.info("No artists found")
            return

        artists = []
        for path in artists_dir.iterdir():
            if path.is_dir() and path.name != "templates":
                artists.append(path.name)

        if not artists:
            logger.info("No artists found")
            return

        logger.info("\nAvailable Artists:")
        for artist in sorted(artists, key=str.lower):
            logger.info(f"- {artist}")

    def start_chat(self, input_list: List[str]) -> None:
        """Start an interactive chat with the loaded artist"""
        if not self.agent:
            logger.info("No artist loaded. Use 'load-artist' first")
            return
        
        print(f"\nChatting with {self.agent.artist_name} (type 'exit' to quit)")
        print("-" * 50)

        while True:
            user_input = input("\nYou: ").strip()
            if user_input.lower() in ['exit', 'quit']:
                break

            response = self.agent.chat(user_input)
            print(f"\n{self.agent.artist_name}: {response}")

    def memory_upload(self, input_list: List[str]) -> None:
        """Upload documents to agent memory"""
        if not self.agent:
            logger.info("No artist loaded. Use 'load-artist' first")
            return
        
        if len(input_list) < 3:
            logger.info("Please specify category and file(s)")
            logger.info("Format: memory-upload {category} file1 [file2...]")
            return

        category = input_list[1]
        filepaths = input_list[2:]

        # Handle wildcards
        import glob
        expanded_paths = []
        for filepath in filepaths:
            expanded = glob.glob(filepath)
            if expanded:
                expanded_paths.extend(expanded)
            else:
                expanded_paths.append(filepath)
        
        if not expanded_paths:
            logger.info("No matching files found")
            return
        
        stats = self.agent.memory.upload_documents(expanded_paths, category)
        logger.info("\nUpload Summary:")
        logger.info(f"Files attempted: {stats['total_attempted']}")
        logger.info(f"Successful: {stats['successful']}")
        logger.info(f"Failed: {stats['failed']}")
        logger.info(f"Total chunks: {stats['total_chunks']}")

    def memory_list(self, input_list: List[str]) -> None:
        """List memory categories or contents"""
        if not self.agent:
            logger.info("No artist loaded. Use 'load-artist' first")
            return
        
        if len(input_list) < 2:
            categories = self.agent.memory.list_categories()
            if not categories:
                logger.info("No memory categories found")
                return
            
            logger.info("\nMemory Categories:")
            for category in sorted(categories):
                stats = self.agent.memory.get_category_stats(category)
                logger.info(f"\n{category}:")
                logger.info(f"  Documents: {stats.document_count}")
                logger.info(f"  Total chunks: {stats.total_chunks}")
            return
        
        category = input_list[1]
        try:
            stats = self.agent.memory.get_category_stats(category)
            logger.info(f"\nContents of '{category}':")
            for doc in stats.documents:
                filename = Path(doc['source']).name
                logger.info(f"\n• {filename}")
                logger.info(f"Chunks: {doc['chunk_count']}")
                logger.info(f"Size: {doc['total_size']:,} characters")
        except Exception as e:
            logger.error(f"Error listing category: {e}")

    def memory_search(self, input_list: List[str]) -> None:
        """Search agent memories"""
        if not self.agent:
            logger.info("No artist loaded. Use 'load-artist' first")
            return
        
        logger.info("Starting search...")

        if len(input_list) < 2:
            logger.info("Please specify a search query")
            logger.info("Format: memory-search 'query' [category]")
            return
        
        # Handle optional category
        categories = self.agent.memory.list_categories()
        category = input_list[-1] if len(input_list) > 2 and input_list[-1] in categories else None

        # Get query
        query_parts = input_list[1:-1] if category else input_list[1:]
        query = ' '.join(query_parts).strip("'\"")

        # Search
        context, results = self.agent.memory.get_relevant_context(
            query=query,
            categories=[category] if category else None
        )

        if not results:
            logger.info(f"No results found for '{query}'")
            return
        
        logger.info(f"\nSearch Results:")
        for i, result in enumerate(results, 1):
            logger.info(f"\n{i}. Score: {result.similarity_score:.2f}")
            logger.info(f"Category: {result.memory.category}")
            logger.info(f"Source: {result.memory.metadata.get('source', 'Unknown')}")
            preview = result.memory.content[:200] + "..." if len(result.memory.content) > 200 else result.memory.content
            logger.info(f"Content: {preview}")

    def memory_wipe(self, input_list: List[str]) -> None:
        """Delete memories"""
        if not self.agent:
            logger.info("No artist loaded. Use 'load-artist' first")
            return
        
        # Wipe everything
        if len(input_list) == 1:
            categories = self.agent.memory.list_categories()
            if not categories:
                logger.info("No memories to wipe")
                return
            
            logger.info("\n⚠️  WARNING: This will delete ALL memories!")
            if input("Type 'yes' to confirm: ").lower() != 'yes':
                logger.info("Operation canceled")
                return
            
            if self.agent.memory.wipe_all_memories():
                logger.info("✅ All memories wiped")
            else:
                logger.error("Failed to wipe memories")
        
        # Wipe category
        category = input_list[1]
        if len(input_list) == 2:
            if category not in self.agent.memory.list_categories():
                logger.info(f"Category '{category}' not found")
                return
            
            logger.info(f"\n⚠️  WARNING: This will delete category '{category}'")
            if input("Type 'yes' to confirm: ").lower() != 'yes':
                logger.info("Operation cancelled")
                return
            
            result = self.agent.memory.wipe_category(category)
            if result['success']:
                logger.info (f"✅ Category '{category}' wiped")
            return
        
        # Wipe specific document
        filename = input_list[2]
        chunks_deleted = self.agent.memory.wipe_document(category, filename)
        if chunks_deleted > 0:
            logger.info(f"✅ Deleted {chunks_deleted} chunks from '{filename}'")
        else:
            logger.info(f"No document found matching '{filename}' in '{category}'")

    def print_h_bar(self):
        """Print a horizontal bar for visual separation"""
        print("─" * 50)

    def run(self) -> None:
        """Start the CLI"""
        self.print_h_bar()
        logger.info("\n👋 Welcome to Maistro CLI!")
        logger.info("Type 'help' for a list of commands\n")
        self.print_h_bar()

        while True:
            try:
                input_string = self.session.prompt(
                    self._get_prompt_message(),
                    style=self.style
                ).strip()

                if input_string:
                    self._handle_command(input_string)
            
            except KeyboardInterrupt:
                continue
            except EOFError:
                self.exit([])
            except Exception as e:
                logger.exception(f"Unexpected error: {e}")

if __name__ == "__main__":
    cli = MaistroCLI()
    cli.run()