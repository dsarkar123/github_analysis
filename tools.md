# src/tools/mongodb_tools.py
from pymongo import MongoClient
import os # For environment variables

class MongoDBDataLoader(BaseTool):
    name: str = "MongoDB Data Loader"
    description: str = "Loads GitHub data (PRs, Issues, Comments) from a MongoDB collection."

    def _run(self, db_name: str, collection_name: str, query: dict = None) -> list:
        # Implement MongoDB connection and data fetching logic here
        # Example (basic):
        try:
            client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017/"))
            db = client[db_name]
            collection = db[collection_name]
            data = list(collection.find(query or {}))
            client.close()
            return data
        except Exception as e:
            return f"Error loading data from MongoDB: {e}"

# src/tools/text_processing_tools.py
import re

class TextCleaner():
    name: str = "Text Cleaner"
    description: str = "Cleans raw text by removing Markdown, HTML tags, and code blocks."

    def _run(self, text: str) -> str:
        # Implement text cleaning logic here
        # Remove code blocks (assuming triple backticks)
        cleaned_text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
        # Remove Markdown formatting (basic)
        cleaned_text = re.sub(r'[*_`~#\-=+>!\[\]()]', '', cleaned_text) # Simplified for example
        # Remove HTML tags (basic)
        cleaned_text = re.sub(r'<[^>]*>', '', cleaned_text)
        # Remove multiple spaces
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
        return cleaned_text

# src/tools/metadata_extractor.py

class MetadataExtractor():
    name: str = "Metadata Extractor"
    description: "Extracts and structures metadata from raw GitHub data records."

    def _run(self, record: dict, record_type: str) -> dict:
        metadata = {
            "type": record_type,
            "repo_name": record.get("repo_name"), # Assuming this is part of your mongo doc
            "author": record.get("user", {}).get("login"), # For issues/PRs/comments
            "timestamp": record.get("created_at"),
            "url": record.get("html_url"),
            # Add specific IDs based on type
        }
        if record_type == "pull_request":
            metadata["github_id"] = record.get("number")
            metadata["title"] = record.get("title")
        elif record_type == "issue":
            metadata["github_id"] = record.get("number")
            metadata["title"] = record.get("title")
        elif record_type == "comment":
            metadata["github_id"] = record.get("id")
            metadata["parent_id"] = record.get("issue_url") or record.get("pull_request_url") # Link to parent
        return metadata
