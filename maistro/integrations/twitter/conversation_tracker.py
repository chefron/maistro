#!/usr/bin/env python3
"""
Conversation Tracker for Twitter interactions.

This module tracks conversation threads between users and the bot,
enabling contextual responses that are aware of the conversation history.
"""

import os
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger('twitter_conversation_tracker')

class ConversationTracker:
    """Tracks conversation threads between users and the bot"""
    
    def __init__(self, cache_dir: str, username: str):
        """
        Initialize the conversation tracker
        
        Args:
            cache_dir: Directory to store conversation data
            username: Bot's Twitter username
        """
        self.cache_dir = cache_dir
        self.bot_username = username
        self.conversations_file = os.path.join(cache_dir, f"{username}_conversations.json")
        self.conversations = {}
        
        # Load existing conversations
        self._load_conversations()
    
    def _load_conversations(self):
        """Load conversations from disk"""
        try:
            if os.path.exists(self.conversations_file):
                with open(self.conversations_file, 'r') as f:
                    file_content = f.read().strip()
                    if file_content:
                        loaded_conversations = json.loads(file_content)
                        # Don't overwrite conversations that are already in memory
                        for thread_id, thread_data in loaded_conversations.items():
                            if thread_id not in self.conversations:
                                self.conversations[thread_id] = thread_data
                            # Otherwise, we keep what's in memory
                        
                logger.info(f"Loaded {len(self.conversations)} conversation threads")
            else:
                self.conversations = {}
                logger.info("No existing conversations found")
        except Exception as e:
            logger.error(f"Error loading conversations: {e}")
            # Don't reset conversations if there's an error
            if not hasattr(self, 'conversations') or self.conversations is None:
                self.conversations = {}
    
    def _save_conversations(self):
        """Save conversations to disk with safeguards"""
        try:
            # First check if we need to merge with existing conversations on disk
            existing_conversations = {}
            if os.path.exists(self.conversations_file):
                try:
                    with open(self.conversations_file, 'r') as f:
                        file_content = f.read().strip()
                        if file_content:
                            existing_conversations = json.loads(file_content)
                except Exception as e:
                    logger.error(f"Error reading existing conversations: {e}")
            
            # Merge with what we have in memory (keeping our in-memory version if there's a conflict)
            merged_conversations = {**existing_conversations, **self.conversations}
            
            # Save the merged result
            with open(self.conversations_file, 'w') as f:
                json.dump(merged_conversations, f, indent=2)
            
            logger.info(f"Saved {len(merged_conversations)} conversation threads")
            
            # Update our in-memory version to include everything
            self.conversations = merged_conversations
        except Exception as e:
            logger.error(f"Error saving conversations: {e}")

    def store_original_tweet(self, tweet_id, text):
        print(f"DIAGNOSTIC: Storing original tweet with ID {tweet_id} and text: {text}")
        """
        Store an original tweet from the bot (not a reply)
        
        Args:
            tweet_id: The ID of the tweet
            text: The content of the tweet
        """
        # Create a new thread with this tweet as the first message
        thread_id = f"thread_{tweet_id}"
        self.conversations[thread_id] = {
            "user": None,  # No user yet, as no one has replied
            "started_at": datetime.now().isoformat(),
            "messages": [{
                "tweet_id": tweet_id,
                "sender": self.bot_username,
                "text": text,
                "timestamp": datetime.now().isoformat(),
                "is_reply_to": None
            }]
        }
        logger.info(f"Stored original tweet {tweet_id} in new thread {thread_id}")
        self._save_conversations()
    
    def add_mention(self, mention, mentions_handler=None):
        """
        Add a mention to the appropriate conversation thread
        
        Args:
            mention: The mention data from Twitter API
            mentions_handler: Optional MentionsHandler for fetching tweets
            
        Returns:
            thread_id: The ID of the thread this mention belongs to
        """
        # Extract key information
        tweet_id = mention["id"]
        username = mention["username"]
        text = mention["text"]
        created_at = mention.get("created_at", datetime.now().isoformat())
        in_reply_to = mention.get("in_reply_to_status_id")
        
        # Determine conversation key (thread_id)
        thread_id = None
        
        # Check if this is a reply to an existing tweet in our threads
        if in_reply_to:
            # Look through all conversations to find the tweet being replied to
            for thread, data in self.conversations.items():
                for msg in data["messages"]:
                    if msg["tweet_id"] == in_reply_to:
                        thread_id = thread
                        break
                if thread_id:
                    break
                    
            # If not found and mentions_handler is provided, try to fetch the original tweet
            if not thread_id and mentions_handler and hasattr(mentions_handler, 'fetch_tweet'):
                try:
                    logger.info(f"Trying to fetch original tweet {in_reply_to}")
                    original_tweet = mentions_handler.fetch_tweet(in_reply_to)
                    if original_tweet:
                        # Check if it's from our bot
                        if original_tweet.get("username") == self.bot_username:
                            # Create a new thread with this tweet as the first message
                            thread_id = f"thread_{in_reply_to}"
                            self.conversations[thread_id] = {
                                "user": username,
                                "started_at": original_tweet.get("created_at", datetime.now().isoformat()),
                                "messages": [{
                                    "tweet_id": original_tweet["id"],
                                    "sender": self.bot_username,
                                    "text": original_tweet["text"],
                                    "timestamp": original_tweet.get("created_at", datetime.now().isoformat()),
                                    "is_reply_to": original_tweet.get("in_reply_to_status_id")
                                }]
                            }
                            logger.info(f"Created new thread with fetched original tweet: {in_reply_to}")
                except Exception as e:
                    logger.error(f"Error fetching original tweet: {e}")
        
        # If no thread found, create a new one
        if not thread_id:
            thread_id = f"{int(time.time())}_{username}_{tweet_id}"
            self.conversations[thread_id] = {
                "user": username,
                "started_at": datetime.now().isoformat(),
                "messages": []
            }
            logger.info(f"Created new conversation thread: {thread_id}")
        
        # Add message to thread
        message = {
            "tweet_id": tweet_id,
            "sender": username,
            "text": text,
            "timestamp": created_at,
            "is_reply_to": in_reply_to
        }
        
        self.conversations[thread_id]["messages"].append(message)
        logger.info(f"Added message to thread {thread_id}: {tweet_id}")
        
        # Save updated conversations
        self._save_conversations()
        
        return thread_id
    
    def add_bot_reply(self, thread_id, tweet_id, text):
        """
        Add the bot's reply to a conversation thread
        
        Args:
            thread_id: The conversation thread ID
            tweet_id: The ID of the bot's reply tweet
            text: The text of the bot's reply
            
        Returns:
            bool: Success indicator
        """
        if thread_id not in self.conversations:
            logger.error(f"Thread {thread_id} not found")
            return False
        
        # Add bot message to thread
        message = {
            "tweet_id": tweet_id,
            "sender": self.bot_username,
            "text": text,
            "timestamp": datetime.now().isoformat(),
            "is_reply_to": self.conversations[thread_id]["messages"][-1]["tweet_id"]
        }
        
        self.conversations[thread_id]["messages"].append(message)
        logger.info(f"Added bot reply to thread {thread_id}: {tweet_id}")
        
        # Save updated conversations
        self._save_conversations()
        
        return True
    
    def get_thread_context(self, thread_id):
        """
        Get formatted conversation history for a thread
        
        Args:
            thread_id: The conversation thread ID
            
        Returns:
            Formatted string with conversation history
        """
        if thread_id not in self.conversations:
            return "No previous conversation history."
        
        thread = self.conversations[thread_id]
        messages = thread["messages"]
        
        # Format thread as a conversation
        context = f"Previous conversation with @{thread['user']}:\n\n"
        
        for msg in messages:
            sender = msg["sender"]
            text = msg["text"].replace('RT @', '').strip()
            
            # Format each message
            if sender == self.bot_username:
                context += f"You: {text}\n\n"
            else:
                context += f"@{sender}: {text}\n\n"
        
        return context
    
    def get_user_history_summary(self, username: str, max_threads: int = 3):
        """
        Get complete previous conversations with a user
        
        Args:
            username: The Twitter username
            max_threads: Maximum number of previous threads to include
            
        Returns:
            A formatted history of past conversations
        """
        # Find all threads with this user
        user_threads = []
        for thread_id, thread_data in self.conversations.items():
            if thread_data["user"] == username:
                # Add thread and its timestamp for sorting
                try:
                    timestamp = datetime.fromisoformat(thread_data["started_at"].replace('Z', '+00:00'))
                except:
                    timestamp = datetime.now() - timedelta(days=30)  # Default old time
                
                user_threads.append((thread_id, thread_data, timestamp))
        
        # Sort threads by time (newest first) and take the most recent ones
        user_threads.sort(key=lambda x: x[2], reverse=True)
        recent_threads = user_threads[:max_threads]
        
        if not recent_threads:
            return "No previous conversations with this user."
        
        # Build complete history
        history = f"PREVIOUS CONVERSATIONS WITH @{username} (NOT PART OF CURRENT THREAD):\n\n"
        
        for i, (thread_id, thread_data, timestamp) in enumerate(recent_threads, 1):
            # Get date in readable format
            date_str = timestamp.strftime("%B %d, %Y")
            
            # Get all messages from this thread
            messages = thread_data["messages"]
            
            # Add thread header
            history += f"Conversation {i} (from {date_str}):\n"
            
            # Include ALL messages from the thread
            for msg in messages:
                if msg['sender'] == self.bot_username:
                    history += f"You: {msg['text']}\n"
                else:
                    history += f"@{msg['sender']}: {msg['text']}\n"
            
            history += "\n"
        
        return history