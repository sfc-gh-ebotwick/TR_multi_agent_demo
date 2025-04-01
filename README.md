# TR_multi_agent_demo

# [Work in Progress] - MVP nearly ready, need to web scraping component of web search agents and clean-up/refine a few things

## Demo of using multiple Snowflake Cortex Services in a multi-agent workflow to prepare Sales Representatives for Upcoming meetings

### Agent 1 - Cortex Analyst - Discover information about a customer's contract and which products they are using
### Agent 2 - Web Search/CortexLLM - Identify top news stories about a customer and summarize articles using Cortex LLM functions
### Agent 3 - Web Search/CortexLLM -  Identify top market trends and news for a customer's industry and summarize articles using Cortex LLM functions
### Agent 4 - Prep Pitch - Generate a sales pitch for the upcoming sales meeting based on output of agents 1-3
### Agent 5 - Discovery Questions - Generate discovery questions for the upcoming sales meeting based on output of agents 1-3

### Pull together all retrieved info and generate a markdown document output for the sales representative to use in preperation of upcoming meetings
