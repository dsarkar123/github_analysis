import streamlit as st
import requests
import pandas as pd
import google.generativeai as genai
from collections import Counter
import plotly.express as px
import plotly.graph_objects as go
import os
import time
import datetime
from dateutil.relativedelta import relativedelta
import pytz

# Configure Gemini API (store your API key securely, e.g., in Streamlit secrets)
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    st.error("Please add your Gemini API key to Streamlit secrets.")
    st.stop()
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')

# GitHub Personal Access Token from Streamlit secrets
GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN")
headers = {'Authorization': f'token {GITHUB_TOKEN}'} if GITHUB_TOKEN else None

def safe_github_request(url, headers=headers):
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 403 and 'Retry-After' in response.headers:
            retry_after = int(response.headers['Retry-After'])
            st.warning(f"GitHub API rate limit hit. Retrying in {retry_after} seconds.")
            time.sleep(retry_after)
            return safe_github_request(url, headers)  # Recursive retry
        elif response.status_code == 200:
            return response
        elif response.status_code == 401:
            st.error("GitHub API: Unauthorized. Please check your Personal Access Token.")
            return None
        elif response.status_code == 404:
            return response  # Let the calling function handle 'Not Found'
        else:
            st.error(f"GitHub API: Failed to fetch data from {url}. Status code: {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        st.error(f"Network error during GitHub API request: {e}")
        return None

def fetch_user_repositories(username):
    url = f'https://api.github.com/users/{username}/repos'
    response = safe_github_request(url)
    if response and response.status_code == 200:
        repos = response.json()
        return repos
    elif response and response.status_code == 404:
        st.error(f"GitHub user '{username}' not found.")
        return []
    return []

def fetch_repository_data(username, repo_name):
    url = f'https://api.github.com/repos/{username}/{repo_name}'
    response = safe_github_request(url)
    if response and response.status_code == 200:
        repo = response.json()
        repo_data = {
            'Name': repo['name'],
            'Description': repo['description'],
            'Stars': repo['stargazers_count'],
            'Forks': repo['forks_count'],
            'Watchers': repo['watchers_count']
        }
        return repo_data
    elif response and response.status_code == 404:
        st.error(f"Repository '{repo_name}' not found for user '{username}'.")
        return None
    return None

def fetch_all_pages(url_base, params=None):
    """
    Fetches all pages of data from a paginated GitHub API endpoint.
    Includes an optional 'params' dictionary to pass to the request.
    """
    results = []
    page = 1
    per_page = 100 # Maximum allowed by GitHub API for most endpoints
    
    progress_text = "Fetching data..."
    my_bar = st.progress(0, text=progress_text)
    
    while True:
        paginated_url = f"{url_base}"
        
        current_params = {'page': page, 'per_page': per_page}
        if params:
            current_params.update(params)

        response = requests.get(paginated_url, headers=headers, params=current_params)
        
        if response.status_code == 403 and 'Retry-After' in response.headers:
            retry_after = int(response.headers['Retry-After'])
            st.warning(f"GitHub API rate limit hit. Retrying in {retry_after} seconds.")
            time.sleep(retry_after)
            continue
        elif response.status_code == 200:
            current_page_data = response.json()
            if not current_page_data:
                break
            results.extend(current_page_data)
            
            my_bar.progress(min(int(page * 10), 99), text=f"Fetched {len(results)} items...") 
            page += 1
        else:
            st.error(f"GitHub API: Failed to fetch data from {paginated_url}. Status code: {response.status_code}. Response: {response.text}")
            break
            
    my_bar.empty()
    return results

def get_commits(username, repo_name, since_date=None, until_date=None):
    url = f'https://api.github.com/repos/{username}/{repo_name}/commits'
    params = {}
    if since_date:
        params['since'] = since_date.isoformat().replace('+00:00', 'Z') 
    if until_date:
        params['until'] = until_date.isoformat().replace('+00:00', 'Z')
    return fetch_all_pages(url, params)

def get_pull_requests(username, repo_name):
    url = f'https://api.github.com/repos/{username}/{repo_name}/pulls?state=all'
    return fetch_all_pages(url) 

def get_issues(username, repo_name):
    url = f'https://api.github.com/repos/{username}/{repo_name}/issues?state=all'
    return fetch_all_pages(url) 


st.set_page_config(page_title='GitHub Analysis with Gemini', layout='wide')

# --- Inject Custom CSS ---
st.markdown(
    """
    <style>
    /* Main container styling for a dark, GitHub-like feel */
    .stApp {
        background-color: #0d1117; /* GitHub Dark Mode background */
        color: #c9d1d9; /* Default text color */
    }

    /* Headers */
    h1, h2, h3, h4, h5, h6 {
        color: #58a6ff; /* A lighter blue for headers */
    }

    /* Sidebar background */
    .css-1d391kg { /* Target Streamlit's sidebar class */
        background-color: #161b22; /* Slightly darker than main content */
    }

    /* Metric boxes */
    [data-testid="stMetric"] {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 6px;
        padding: 15px;
        margin-bottom: 10px;
    }

    /* Metric labels */
    [data-testid="stMetricLabel"] {
        color: #8b949e; /* Muted text for labels */
        font-size: 0.9em;
    }
    
    /* Metric values */
    [data-testid="stMetricValue"] {
        color: #c9d1d9;
        font-size: 1.8em;
        font-weight: 600;
    }

    /* Info boxes/warnings */
    .stAlert {
        background-color: #1a1e23;
        border-left: 5px solid #58a6ff; /* Blue border for info */
        color: #c9d1d9;
    }
    
    /* Dataframe styling */
    .stDataFrame {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 6px;
    }

    /* Expander styling */
    .streamlit-expanderHeader {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 6px;
        color: #58a6ff;
    }

    /* Links */
    a {
        color: #58a6ff; /* GitHub link blue */
        text-decoration: none;
    }
    a:hover {
        text-decoration: underline;
    }
    
    /* Horizontal rule (separator) */
    hr {
        border-top: 1px solid #30363d;
    }

    /* Specific colors for metrics (optional, can be done with HTML if needed) */
    /* Example for active PRs - this targets the specific value span */
    /* You'd need to manually wrap the value in HTML or find its unique class */
    .stMetric[data-testid="stMetric"]:nth-child(1) [data-testid="stMetricValue"] {
        color: #3fb950; /* Green for active */
    }
    /* Merged PRs */
    .stMetric[data-testid="stMetric"]:nth-child(2) [data-testid="stMetricValue"] {
        color: #8957e5; /* Purple for merged */
    }
    /* Open Issues */
    .stMetric[data-testid="stMetric"]:nth-child(3) [data-testid="stMetricValue"] {
        color: #cc6045; /* Reddish for open issues */
    }
    /* Closed Issues */
    .stMetric[data-testid="stMetric"]:nth-child(4) [data-testid="stMetricValue"] {
        color: #8b949e; /* Gray for closed */
    }


    </style>
    """,
    unsafe_allow_html=True
)

st.title('✨ GitHub Analysis ')
st.markdown("""
    <p style='color:#8b949e;'>Explore GitHub pull requests, issues, and comments !!
    Enter a GitHub username and optionally a repository name to get started.</p>
""", unsafe_allow_html=True)


with st.sidebar:
    st.header('Input Parameters')
    username = st.text_input('Enter GitHub Username', help="GitHub username of the account you want to analyze.")
    repo_name = st.text_input('Enter Repository Name (optional)', help="Specific repository name to get detailed insights.")

    st.header('Time Period Filter')
    time_period_option = st.selectbox(
        "Select a time period",
        ("Last 1 Week", "Last 1 Day", "Last 1 Month", "Custom Date Range"),
        index=0 # Default to Last 1 Week
    )

    today = datetime.date.today()
    start_date_filter = None
    end_date_filter = today

    if time_period_option == "Last 1 Week":
        start_date_filter = today - datetime.timedelta(weeks=1)
    elif time_period_option == "Last 1 Day":
        start_date_filter = today - datetime.timedelta(days=1)
    elif time_period_option == "Last 1 Month":
        start_date_filter = today - relativedelta(months=1)
    elif time_period_option == "Custom Date Range":
        col1_s, col2_s = st.columns(2) # Renamed to avoid conflict
        with col1_s:
            custom_start_date = st.date_input("Start date", value=today - datetime.timedelta(weeks=1))
        with col2_s:
            custom_end_date = st.date_input("End date", value=today)
        
        if custom_start_date > custom_end_date:
            st.error("Error: End date must be after or equal to start date.")
            start_date_filter = None
        else:
            start_date_filter = custom_start_date
            end_date_filter = custom_end_date

    utc_timezone = pytz.utc
    since_datetime_utc = None
    until_datetime_utc = None

    if start_date_filter:
        since_datetime_utc = utc_timezone.localize(datetime.datetime.combine(start_date_filter, datetime.time.min))
    if end_date_filter:
        until_datetime_utc = utc_timezone.localize(datetime.datetime.combine(end_date_filter, datetime.time.max))

    st.markdown(f"<p style='font-size:0.9em; color:#8b949e;'>Data will be filtered from <b>{start_date_filter}</b> to <b>{end_date_filter}</b> (inclusive).</p>", unsafe_allow_html=True)


if username:
    if repo_name:
        st.markdown(f"## Repository: <span style='color:#58a6ff;'>{username}/{repo_name}</span>", unsafe_allow_html=True)

        st.markdown(f"<h3 style='color:#c9d1d9;'>📅 Pulse: {start_date_filter.strftime('%b %d, %Y')} - {end_date_filter.strftime('%b %d, %Y')}</h3>", unsafe_allow_html=True)

        all_commits = []
        all_pull_requests = []
        all_issues = []

        with st.spinner("Fetching all data for analysis... This might take a while for large repositories."):
            all_commits = get_commits(username, repo_name, since_datetime_utc, until_datetime_utc)
            all_pull_requests = get_pull_requests(username, repo_name)
            all_issues = get_issues(username, repo_name)

        filtered_prs = []
        for pr in all_pull_requests:
            created_at = datetime.datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00')) 
            if since_datetime_utc and created_at < since_datetime_utc:
                continue
            if until_datetime_utc and created_at > until_datetime_utc:
                continue
            filtered_prs.append(pr)

        filtered_issues = []
        for issue in all_issues:
            created_at = datetime.datetime.fromisoformat(issue['created_at'].replace('Z', '+00:00'))
            if since_datetime_utc and created_at < since_datetime_utc:
                continue
            if until_datetime_utc and created_at > until_datetime_utc:
                        continue
            # Exclude pull requests from issues list for accurate issue counts
            if 'pull_request' not in issue:
                filtered_issues.append(issue)

        # --- Display Summary Metrics (mimicking Pulse) ---
        st.markdown("### 📊 Overview")
        col1, col2, col3 = st.columns(3)

        with col1:
            active_prs = [pr for pr in filtered_prs if pr['state'] == 'open']
            st.metric(label="Active Pull Requests", value=len(active_prs))
        with col2:
            merged_prs = [pr for pr in filtered_prs if pr['state'] == 'closed' and pr['merged_at']]
            st.metric(label="Merged Pull Requests", value=len(merged_prs))
        with col3:
            open_issues_count = len([issue for issue in filtered_issues if issue['state'] == 'open'])
            st.metric(label="Open Issues", value=open_issues_count)

        col4, col5, col6 = st.columns(3) # Added one more column for layout consistency

        with col4:
            closed_issues_count = len([issue for issue in filtered_issues if issue['state'] == 'closed'])
            st.metric(label="Closed Issues", value=closed_issues_count)
        with col5:
            st.metric(label="Total Commits", value=len(all_commits))
        with col6:
            # Placeholder for another metric if needed, or leave empty
            st.markdown("&nbsp;") # Non-breaking space to keep column structure

        st.markdown("---") 

        # --- Contributors ---
        st.markdown("### 🧑‍💻 Top Contributors")
        if all_commits:
            commit_authors = []
            for commit in all_commits:
                if commit['commit']['author'] and commit['commit']['author']['name']:
                    commit_authors.append(commit['commit']['author']['name'])
                elif commit['author'] and commit['author']['login']: # Fallback for commit author if needed
                    commit_authors.append(commit['author']['login'])

            if commit_authors:
                author_counts = Counter(commit_authors)
                top_authors = author_counts.most_common(5) # Top 5 contributors
                for author, count in top_authors:
                    st.markdown(f"- <span style='color:#58a6ff;'>**{author}**</span>: {count} commits", unsafe_allow_html=True)
            else:
                st.info("No author information found for commits in this period.")
        else:
            st.info("No commits to analyze contributors for this period.")

        st.markdown("---") 

        # --- Recent Activity (mimicking GitHub's display) ---
        st.markdown("### 📈 Recent Activity")

        all_recent_events = []

        for pr in filtered_prs:
            all_recent_events.append({
                'type': 'Pull Request',
                'title': pr['title'],
                'user': pr['user']['login'],
                'url': pr['html_url'],
                'created_at': datetime.datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00'))
            })
        
        for issue in filtered_issues:
            # 'pull_request' key exists for PRs when fetched via issues endpoint
            if 'pull_request' not in issue:
                all_recent_events.append({
                    'type': 'Issue',
                    'title': issue['title'],
                    'user': issue['user']['login'],
                    'url': issue['html_url'],
                    'created_at': datetime.datetime.fromisoformat(issue['created_at'].replace('Z', '+00:00'))
                })

        for commit in all_commits:
            all_recent_events.append({
                'type': 'Commit',
                'title': commit['commit']['message'].split('\n')[0],
                'user': commit['commit']['author']['name'] if commit['commit']['author'] else 'N/A',
                'url': commit['html_url'],
                'created_at': datetime.datetime.fromisoformat(commit['commit']['author']['date'].replace('Z', '+00:00'))
            })
        
        if all_recent_events:
            all_recent_events.sort(key=lambda x: x['created_at'], reverse=True)
            
            num_events_to_show = 15 # Show more recent events
            for i, event in enumerate(all_recent_events[:num_events_to_show]):
                type_color = ""
                if event['type'] == 'Pull Request':
                    type_color = "#3fb950" # Green
                elif event['type'] == 'Issue':
                    type_color = "#cc6045" # Reddish
                elif event['type'] == 'Commit':
                    type_color = "#8b949e" # Grayish
                
                st.markdown(
                    f"<span style='color:{type_color};'>**{event['type']}**</span>: <a href='{event['url']}' target='_blank' style='color:#58a6ff;'>{event['title']}</a> by <span style='color:#c9d1d9;'>{event['user']}</span> on <span style='color:#8b949e;'>{event['created_at'].strftime('%Y-%m-%d %H:%M')}</span>",
                    unsafe_allow_html=True
                )
                if i < num_events_to_show - 1:
                    st.markdown("---")
        else:
            st.info("No recent activity found in the selected time frame.")

        st.markdown("---") 

        # --- Raw data display (in an expander) ---
        with st.expander("Show Raw Data (for debugging)"):
            st.subheader("Raw Commits Data")
            st.json(all_commits)
            st.subheader("Raw Pull Requests Data")
            st.json(all_pull_requests)
            st.subheader("Raw Issues Data")
            st.json(all_issues)

    else:
        st.info('Please enter a GitHub username and optionally a repository name to get started.')
else:
    st.info('Please enter a GitHub username to get started.')