from pathlib import Path
import logging
import os
from dataclasses import dataclass
from typing import Callable, Dict, List
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory

from maistro.core.agent import MusicAgent
from maistro.integrations.chat.handler import chat_session
from maistro.integrations.youtube.engagement import AgentResponder, CommentMonitor
from maistro.integrations.twitter import (
    TwitterAuth, APITwitterPost, start_scheduler, 
    stop_scheduler, start_mentions_checker, 
    stop_mentions_checker, ConversationTracker
)


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

        # Flag to track active chat session
        self.in_chat_session = False

        # Initialize YouTube monitoring
        self.youtube_monitor = None
        self.youtube_responder = None

        # Initialize Twitter monitoring
        self.twitter_auth = None
        self.twitter_scheduler_thread = None
        self.twitter_mentions_thread = None
        self.twitter_conversation_tracker = None

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

        # Integration commands
        self._register_command(
            Command(
                name="chat",
                description="Chat with the artist",
                tips="Use 'exit' or 'quit' to end the chat session",
                handler=self.start_chat,
                aliases=['talk']
            )
        )

        self._register_command(
            Command(
                name="start-youtube",
                description="Start YouTube comment monitoring and auto-responses",
                tips=["Starts a background process that monitors your YouTube channel",
                      "and automatically responds to new comments using the loaded artist"],
                handler=self.start_youtube_monitoring,
                aliases=['youtube-start', 'monitor-youtube']
            )
        )

        self._register_command(
            Command(
                name="stop-youtube",
                description="Stop YouTube comment monitoring",
                tips=["Stops the background YouTube monitoring process"],
                handler=self.stop_youtube_monitoring,
                aliases=['youtube-stop']
            )
        )

        self._register_command(
            Command(
                name="start-twitter",
                description="Start Twitter posting and mention monitoring",
                tips=["Starts automatic tweet posting and mention monitoring"],
                handler=self.start_twitter_integration,
                aliases=['twitter-start']
            )
        )

        self._register_command(
            Command(
                name="stop-twitter",
                description="Stop Twitter posting and mention monitoring",
                tips=["Stops all Twitter background processes"],
                handler=self.stop_twitter_integration,
                aliases=['twitter-stop']
            )
        )

        # Memory commands
        self._register_command(
            Command(
                name="memory-upload",
                description="Upload documents to artist's memory",
                tips=["Format: memory-upload {category} file1 [file2...]",
                      "Example categories: songs, feedback, analytics, metrics, analysis"],
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

        self._register_command(
            Command(
                name="update-stats",
                description="Update streaming stats in memory",
                tips=["Updates and stores latest streaming and token statistics in memory from connected platforms"],
                handler=self.update_stats,
                aliases=['stats-update']
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

        chat_session(self.agent)

    def start_youtube_monitoring(self, input_list: List[str]) -> None:
        """Start monitoring YouTube comments and respond automatically"""
        if not self.agent:
            logger.info("No artist loaded. Use 'load-artist' first")
            return
        
        # Check if monitoring is already running
        if hasattr(self, 'youtube_monitor') and self.youtube_monitor and getattr(self.youtube_monitor, '_running', False):
            logger.info("YouTube monitoring is already running")
            return
        
        # Initialize the monitor and responder if needed
        if not hasattr(self, 'youtube_monitor') or not self.youtube_monitor:
            self.youtube_monitor = CommentMonitor()
        
        if not hasattr(self, 'youtube_responder') or not self.youtube_responder:
            self.youtube_responder = AgentResponder(self.agent)
        
        # Check OAuth is properly set up
        if not self.youtube_monitor.initialize_oauth():
            logger.error("Failed to initialize YouTube OAuth. Please check your credentials.")
            return
        
        # Start monitoring
        interval = 300  # Check every 5 minutes by default
        if len(input_list) > 1:
            try:
                interval = int(input_list[1]) * 60  # Convert minutes to seconds
            except ValueError:
                logger.warning(f"Invalid interval '{input_list[1]}', using default 2 minutes")
        
        success = self.youtube_monitor.start(
            callback=self.youtube_responder.handle_comment,
            interval=interval
        )
        
        if success:
            logger.info(f"✅ Started YouTube monitoring with {self.agent.artist_name}")
            logger.info(f"Checking for new comments every {interval//60} minutes")
        else:
            logger.error("Failed to start YouTube monitoring")

    def stop_youtube_monitoring(self, input_list: List[str]) -> None:
        """Stop YouTube comment monitoring"""
        if not hasattr(self, 'youtube_monitor') or not self.youtube_monitor:
            logger.info("YouTube monitoring is not initialized")
            return
        
        if self.youtube_monitor.stop():
            logger.info("✅ Stopped YouTube monitoring")
        else:
            logger.info("YouTube monitoring is not currently running")

    def start_twitter_integration(self, input_list: List[str]) -> None:
        """Start Twitter posting and mentions monitoring"""
        if not self.agent:
            logger.info("No artist loaded. Use 'load-artist' first")
            return
        
        # Check for Twitter credentials
        username = os.getenv('TWITTER_USERNAME')
        password = os.getenv('TWITTER_PASSWORD')
        email = os.getenv('TWITTER_EMAIL')
        two_factor_secret = os.getenv('TWITTER_2FA_SECRET')
        
        if not username or not password:
            logger.error("Twitter credentials not found. Please set TWITTER_USERNAME and TWITTER_PASSWORD in your .env file")
            return
        
        # Initialize Twitter auth
        logger.info("\nInitializing Twitter authentication...")
        try:
            self.twitter_auth = TwitterAuth()
            login_success = self.twitter_auth.login_with_retry(username, password, email, two_factor_secret)
            
            if not login_success:
                logger.error("Failed to log in to Twitter. Please check your credentials.")
                return
                
            logger.info("✅ Successfully logged in to Twitter")
        except Exception as e:
            logger.error(f"Twitter authentication error: {e}")
            return
        
        # Create shared conversation tracker
        cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')
        os.makedirs(cache_dir, exist_ok=True)
        self.twitter_conversation_tracker = ConversationTracker(cache_dir, self.twitter_auth.username)
        logger.info(f"Created shared conversation tracker for @{self.twitter_auth.username}")
        
        # Start tweet scheduler
        logger.info("\nStarting tweet scheduler...")
        
        # Create tweet generator function
        def generate_tweet():
            try:
                api_poster = APITwitterPost(auth=self.twitter_auth, conversation_tracker=self.twitter_conversation_tracker)
                return api_poster.generate_tweet(self.agent)
            except Exception as e:
                logger.error(f"Error generating tweet: {e}")
                return "Error generating tweet"
        
        try:
            self.twitter_scheduler_thread = start_scheduler(
                auth=self.twitter_auth,
                content_generator=generate_tweet
            )
            logger.info("✅ Tweet scheduler started")
        except Exception as e:
            logger.error(f"Error starting tweet scheduler: {e}")
        
        # Start mentions checker
        logger.info("\nStarting mentions checker...")
        
        try:
            self.twitter_mentions_thread = start_mentions_checker(
                auth=self.twitter_auth,
                agent=self.agent,
                conversation_tracker=self.twitter_conversation_tracker
            )
            logger.info("✅ Mentions checker started")
        except Exception as e:
            logger.error(f"Error starting mentions checker: {e}")
        
        logger.info("\nTwitter integration running in background. Use 'stop-twitter' to stop.")

    def stop_twitter_integration(self, input_list: List[str]) -> None:
        """Stop Twitter posting and mentions monitoring"""
        stopped_anything = False
        
        # Stop tweet scheduler
        if stop_scheduler():
            logger.info("✅ Stopped tweet scheduler")
            self.twitter_scheduler_thread = None
            stopped_anything = True
        
        # Stop mentions checker
        if stop_mentions_checker():
            logger.info("✅ Stopped mentions checker")
            self.twitter_mentions_thread = None
            stopped_anything = True
        
        if not stopped_anything:
            logger.info("No Twitter processes were running")
        else:
            logger.info("Twitter integration stopped")

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
        
        logger.info("\nSearch Results:")
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
        elif len(input_list) == 2:
            category = input_list[1]
            if category not in self.agent.memory.list_categories():
                logger.info(f"Category '{category}' not found")
                return
            
            logger.info(f"\n⚠️  WARNING: This will delete category '{category}'")
            if input("Type 'yes' to confirm: ").lower() != 'yes':
                logger.info("Operation cancelled")
                return
            
            result = self.agent.memory.wipe_category(category)
            if result['success']:
                logger.info(f"✅ Category '{category}' wiped")
                
        # Wipe specific document
        elif len(input_list) == 3:
            category = input_list[1]
            filename = input_list[2]
            chunks_deleted = self.agent.memory.wipe_document(category, filename)
            if chunks_deleted > 0:
                logger.info(f"✅ Deleted {chunks_deleted} chunks from '{filename}'")
            else:
                logger.info(f"No document found matching '{filename}' in '{category}'")
        
        else:
            logger.info("Invalid number of arguments for memory-wipe")
        
    def update_stats(self, input_list: List[str]) -> None:
        """Update streaming statistics in memory"""
        if not self.agent:
            logger.info("No artist loaded. Use 'load-artist' first")
            return
        
        from maistro.core.analytics import PlatformStats
        stats_handler = PlatformStats(self.agent.memory)
        success = stats_handler.update_all_stats()
        
        if success:
            logger.info("✅ Streaming statistics updated successfully")
        else:
            logger.error("Failed to update streaming statistics")

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