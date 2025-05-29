#!/usr/bin/env python3
"""
Enhanced GitHub API to MongoDB Data Collection Application

Now includes:
- Structured data formats matching your requirements
- Contributor activity tracking
- All requested fields for PRs, issues, and comments
"""

import os
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from dotenv import load_dotenv

import requests
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.collection import Collection
from pymongo.database import Database

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class GitHubConfig:
    """Configuration for GitHub API access"""
    token: str
    base_url: str = "https://api.github.com"
    requests_per_hour: int = 5000  # GitHub API rate limit
    
class GitHubAPIClient:
    """Enhanced GitHub API client with additional data collection methods"""
    
    def __init__(self, config: GitHubConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'token {config.token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'GitHub-MongoDB-Collector/2.0'
        })
        self.rate_limit_remaining = config.requests_per_hour
        self.rate_limit_reset = time.time() + 3600
    
    def _check_rate_limit(self):
        """Check and handle rate limiting"""
        if self.rate_limit_remaining <= 1:
            sleep_time = max(0, self.rate_limit_reset - time.time())
            if sleep_time > 0:
                logger.warning(f"Rate limit reached, sleeping for {sleep_time:.2f} seconds")
                time.sleep(sleep_time)
    
    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make a request to GitHub API with error handling"""
        self._check_rate_limit()
        
        url = f"{self.config.base_url}{endpoint}"
        
        try:
            response = self.session.get(url, params=params or {})
            
            # Update rate limit info
            self.rate_limit_remaining = int(response.headers.get('X-RateLimit-Remaining', 0))
            self.rate_limit_reset = int(response.headers.get('X-RateLimit-Reset', time.time() + 3600))
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")
            raise
    
    def get_repository_details(self, owner: str, repo: str) -> Dict:
        """Get details for a specific repository."""
        return self._make_request(f"/repos/{owner}/{repo}")

    def get_commits(self, owner: str, repo: str, per_page: int = 100) -> List[Dict]:
        """Get commits for a repository"""
        commits = []
        page = 1
        
        while True:
            try:
                data = self._make_request(
                    f"/repos/{owner}/{repo}/commits",
                    params={'per_page': per_page, 'page': page}
                )
                
                if not data:
                    break
                    
                commits.extend(data)
                page += 1
                
                if len(data) < per_page:
                    break
                    
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 409:  # Empty repository
                    logger.info(f"Repository {owner}/{repo} is empty")
                    break
                raise
        
        return commits
    
    def get_contributors(self, owner: str, repo: str) -> List[Dict]:
        """Get contributors for a repository with their activity stats"""
        try:
            return self._make_request(f"/repos/{owner}/{repo}/contributors")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"Contributors not found for {owner}/{repo}")
                return []
            raise
    
    def get_pull_requests(self, owner: str, repo: str, state: str = 'all') -> List[Dict]:
        """Get pull requests for a repository with full details"""
        prs = []
        page = 1
        
        while True:
            data = self._make_request(
                f"/repos/{owner}/{repo}/pulls",
                params={'state': state, 'per_page': 100, 'page': page}
            )
            
            if not data:
                break
                
            # Get full PR details for each PR
            for pr in data:
                full_pr = self._make_request(f"/repos/{owner}/{repo}/pulls/{pr['number']}")
                prs.append(full_pr)
            
            page += 1
            
            if len(data) < 100:
                break
        
        return prs
    
    def get_issues(self, owner: str, repo: str, state: str = 'all') -> List[Dict]:
        """Get issues for a repository (excluding PRs)"""
        issues = []
        page = 1
        
        while True:
            data = self._make_request(
                f"/repos/{owner}/{repo}/issues",
                params={'state': state, 'per_page': 100, 'page': page}
            )
            
            if not data:
                break
                
            for issue in data:
                # Skip pull requests (GitHub API returns PRs as issues)
                if 'pull_request' not in issue:
                    issues.append(issue)
            
            page += 1
            
            if len(data) < 100:
                break
        
        return issues
    
    def get_issue_comments(self, owner: str, repo: str, issue_number: int) -> List[Dict]:
        """Get comments for a specific issue"""
        comments = []
        page = 1
        while True:
            data = self._make_request(
                f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
                params={'per_page': 100, 'page': page}
            )
            if not data:
                break
            comments.extend(data)
            page += 1
            if len(data) < 100:
                break
        return comments
    
    def get_pr_comments(self, owner: str, repo: str, pr_number: int) -> List[Dict]:
        """Get review comments for a specific pull request"""
        comments = []
        page = 1
        while True:
            data = self._make_request(
                f"/repos/{owner}/{repo}/pulls/{pr_number}/comments",
                params={'per_page': 100, 'page': page}
            )
            if not data:
                break
            comments.extend(data)
            page += 1
            if len(data) < 100:
                break
        return comments
    
    def get_pr_reviews(self, owner: str, repo: str, pr_number: int) -> List[Dict]:
        """Get reviews for a specific pull request"""
        reviews = []
        page = 1
        while True:
            data = self._make_request(
                f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
                params={'per_page': 100, 'page': page}
            )
            if not data:
                break
            reviews.extend(data)
            page += 1
            if len(data) < 100:
                break
        return reviews
    
    def get_contributor_activity(self, owner: str, repo: str, username: str) -> Dict:
        """Get detailed activity for a specific contributor"""
        try:
            # Get weekly commit count
            stats = self._make_request(f"/repos/{owner}/{repo}/stats/contributors")
            user_stats = next((s for s in stats if s['author']['login'] == username), None)
            
            # Get all user contributions
            events = self._make_request(f"/repos/{owner}/{repo}/events")
            user_events = [e for e in events if e.get('actor', {}).get('login') == username]
            
            return {
                'weekly_stats': user_stats,
                'recent_activity': user_events[-50:] if user_events else []  # Last 50 events
            }
        except Exception as e:
            logger.error(f"Failed to get contributor activity for {username}: {e}")
            return {}

class MongoDBManager:
    """Enhanced MongoDB manager with structured data formats"""
    
    def __init__(self, connection_string: str, database_name: str):
        try:
            self.client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
            # Test the connection
            self.client.admin.command('ping')
            logger.info("Successfully connected to MongoDB")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise
            
        self.db: Database = self.client[database_name]
        self._setup_collections()
    
    def _setup_collections(self):
        """Setup MongoDB collections with indexes"""
        collections = {
            'pull_requests': [
                ('pr_id', ASCENDING),
                ('repository_id', ASCENDING),
                ('pr_state', ASCENDING),
                ('pr_created_at', DESCENDING)
            ],
            'issues': [
                ('issue_id', ASCENDING),
                ('repository_id', ASCENDING),
                ('issue_state', ASCENDING),
                ('issue_created_at', DESCENDING)
            ],
            'comments': [
                ('comment_id', ASCENDING),
                ('repository_id', ASCENDING),
                ('comment_parent_type', ASCENDING),
                ('comment_created_at', DESCENDING)
            ],
            'contributor_activity': [
                ('username', ASCENDING),
                ('repository_id', ASCENDING),
                ('last_updated', DESCENDING)
            ]
        }
        
        for collection_name, indexes in collections.items():
            collection = self.db[collection_name]
            for index in indexes:
                try:
                    collection.create_index([index])
                except Exception as e:
                    logger.warning(f"Failed to create index {index} on {collection_name}: {e}")
    
    def _add_timestamp(self, document: Dict) -> Dict:
        """Add collection timestamp to document"""
        document['collected_at'] = datetime.now(timezone.utc)
        return document
    
    def store_pull_requests(self, repository_id: int, pull_requests: List[Dict]) -> List[int]:
        """Store pull requests in the requested format"""
        if not pull_requests:
            return []
        
        collection: Collection = self.db.pull_requests
        pr_numbers = []
        
        for pr in pull_requests:
            # Transform to match requested format
            formatted_pr = {
                'pr_id': pr['id'],
                'pr_number': pr['number'],
                'repository_id': repository_id,
                'pr_title': pr['title'],
                'pr_description': pr['body'],
                'pr_author': pr['user']['login'],
                'pr_created_at': pr['created_at'],
                'pr_merged_at': pr.get('merged_at'),
                'pr_closed_at': pr.get('closed_at'),
                'pr_state': 'merged' if pr.get('merged') else pr['state'],
                'pr_files_changed': pr.get('changed_files', 0),
                'pr_additions': pr.get('additions', 0),
                'pr_deletions': pr.get('deletions', 0),
                'pr_review_comments': pr.get('review_comments', 0),
                'pr_commits': pr.get('commits', 0),
                'pr_linked_issues': [issue['url'] for issue in pr.get('closing_issues', [])],
                'pr_head': {
                    'ref': pr['head']['ref'],
                    'sha': pr['head']['sha']
                },
                'pr_base': {
                    'ref': pr['base']['ref'],
                    'sha': pr['base']['sha']
                }
            }
            
            formatted_pr = self._add_timestamp(formatted_pr)
            
            # Upsert pull request
            result = collection.update_one(
                {'pr_id': formatted_pr['pr_id']},
                {'$set': formatted_pr},
                upsert=True
            )
            
            pr_numbers.append(formatted_pr['pr_number'])
        
        logger.info(f"Stored {len(pull_requests)} pull requests for repository {repository_id}")
        return pr_numbers
    
    def store_issues(self, repository_id: int, issues: List[Dict]) -> List[int]:
        """Store issues in the requested format"""
        if not issues:
            return []
        
        collection: Collection = self.db.issues
        issue_numbers = []
        
        for issue in issues:
            # Transform to match requested format
            formatted_issue = {
                'issue_id': issue['id'],
                'issue_number': issue['number'],
                'repository_id': repository_id,
                'issue_title': issue['title'],
                'issue_description': issue['body'],
                'issue_author': issue['user']['login'],
                'issue_created_at': issue['created_at'],
                'issue_closed_at': issue.get('closed_at'),
                'issue_state': issue['state'],
                'issue_labels': [label['name'] for label in issue.get('labels', [])],
                'issue_comments_count': issue.get('comments', 0),
                'issue_assignees': [assignee['login'] for assignee in issue.get('assignees', [])],
                'issue_milestone': issue.get('milestone', {}).get('title') if issue.get('milestone') else None
            }
            
            formatted_issue = self._add_timestamp(formatted_issue)
            
            # Upsert issue
            result = collection.update_one(
                {'issue_id': formatted_issue['issue_id']},
                {'$set': formatted_issue},
                upsert=True
            )
            
            issue_numbers.append(formatted_issue['issue_number'])
        
        logger.info(f"Stored {len(issue_numbers)} issues for repository {repository_id}")
        return issue_numbers
    
    def store_comments(self, repository_id: int, comments: List[Dict], 
                      parent_type: Optional[str] = None,
                      parent_number: Optional[int] = None) -> List[int]:
        """Store comments in the requested format"""
        if not comments:
            return []
        
        collection: Collection = self.db.comments
        comment_ids = []
        
        for comment in comments:
            # Transform to match requested format
            formatted_comment = {
                'comment_id': comment['id'],
                'repository_id': repository_id,
                'comment_author': comment['user']['login'],
                'comment_created_at': comment.get('created_at'),
                'comment_updated_at': comment.get('updated_at'),
                'comment_body': comment['body'],
                'comment_parent_type': parent_type,  # 'PR' or 'Issue'
                'comment_parent_number': parent_number,
                'comment_parent_id': comment.get('in_reply_to_id')
            }
            
            formatted_comment = self._add_timestamp(formatted_comment)
            
            # Upsert comment
            result = collection.update_one(
                {'comment_id': formatted_comment['comment_id']},
                {'$set': formatted_comment},
                upsert=True
            )
            
            comment_ids.append(formatted_comment['comment_id'])
        
        logger.info(f"Stored {len(comments)} comments for repository {repository_id}")
        return comment_ids
    
    def store_contributor_activity(self, repository_id: int, username: str, activity_data: Dict) -> bool:
        """Store contributor activity data"""
        if not activity_data:
            return False
        
        weekly_stats = activity_data.get('weekly_stats', {})
        if weekly_stats and 'weeks' in weekly_stats:
            for week in weekly_stats['weeks']:
                week['week_start'] = datetime.fromtimestamp(week['w'], tz=timezone.utc).isoformat()
        collection: Collection = self.db.contributor_activity
        
        formatted_activity = {
            'username': username,
            'repository_id': repository_id,
            'weekly_stats': weekly_stats,
            'recent_activity': activity_data.get('recent_activity', []),
            'last_updated': datetime.now(timezone.utc)
        }
        
        # Upsert activity data
        result = collection.update_one(
            {'username': username, 'repository_id': repository_id},
            {'$set': formatted_activity},
            upsert=True
        )
        
        logger.info(f"Stored activity data for contributor {username} in repository {repository_id}")
        return result.acknowledged

class GitHubDataCollector:
    """Enhanced data collector with contributor activity tracking"""
    
    def __init__(self, github_config: GitHubConfig, mongodb_manager: MongoDBManager):
        self.github_client = GitHubAPIClient(github_config)
        self.mongodb_manager = mongodb_manager
    
    def collect_data_for_repository(self, owner: str, repo_name: str, include_comments: bool = True):
        """Collect data for a specific GitHub repository"""
        logger.info(f"Starting data collection for repository: {owner}/{repo_name}")
        
        # Get repository details first to get the repo_id
        try:
            repo_details = self.github_client.get_repository_details(owner, repo_name)
            repo_id = repo_details['id']
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.error(f"Repository {owner}/{repo_name} not found. Please check the owner and repository name.")
                return
            raise

        logger.info(f"Processing repository: {owner}/{repo_name} (ID: {repo_id})")
        
        # Get and store pull requests
        pull_requests = self.github_client.get_pull_requests(owner, repo_name)
        pr_numbers = self.mongodb_manager.store_pull_requests(repo_id, pull_requests)
        
        # Get and store issues
        issues = self.github_client.get_issues(owner, repo_name)
        issue_numbers = self.mongodb_manager.store_issues(repo_id, issues)
        
        # Get and store comments if requested
        if include_comments:
            # Issue comments
            for issue_number in issue_numbers:
                comments = self.github_client.get_issue_comments(owner, repo_name, issue_number)
                self.mongodb_manager.store_comments(repo_id, comments, 'Issue', issue_number)
            
            # PR comments
            for pr_number in pr_numbers:
                comments = self.github_client.get_pr_comments(owner, repo_name, pr_number)
                self.mongodb_manager.store_comments(repo_id, comments, 'PR', pr_number)
                
                # PR reviews (special type of comments)
                reviews = self.github_client.get_pr_reviews(owner, repo_name, pr_number)
                self.mongodb_manager.store_comments(repo_id, reviews, 'PR', pr_number)
        
        # Get and store contributor activity
        contributors = self.github_client.get_contributors(owner, repo_name)
        for contributor in contributors:
            username = contributor['login']
            activity_data = self.github_client.get_contributor_activity(owner, repo_name, username)
            self.mongodb_manager.store_contributor_activity(repo_id, username, activity_data)
        
        logger.info(f"Completed data collection for repository: {owner}/{repo_name}")

def main():
    """Main function"""
    # Configuration
    github_token = os.getenv('GITHUB_TOKEN')
    mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
    database_name = os.getenv('DATABASE_NAME', 'github_data')
    
    # Specific repository details
    target_owner = "amazingandyyy"
    target_repo = "mern"

    if not github_token:
        raise ValueError("GITHUB_TOKEN environment variable is required")
    
    logger.info(f"Connecting to MongoDB: {mongodb_uri}")
    logger.info(f"Target GitHub repository: {target_owner}/{target_repo}")
    logger.info(f"Target MongoDB database: {database_name}")
    
    # Initialize components
    github_config = GitHubConfig(token=github_token)
    mongodb_manager = MongoDBManager(mongodb_uri, database_name)
    collector = GitHubDataCollector(github_config, mongodb_manager)
    
    # Collect data for the specific repository
    try:
        collector.collect_data_for_repository(target_owner, target_repo, include_comments=True)
        logger.info("Data collection completed successfully")
    except Exception as e:
        logger.error(f"Data collection failed: {e}")
        raise

if __name__ == "__main__":
    main()