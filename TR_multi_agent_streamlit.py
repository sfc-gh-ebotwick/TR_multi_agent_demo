import streamlit as st
import pandas as pd
import numpy as np
import random
import json
import time

#Create snowflake session
from snowflake.snowpark.context import get_active_session
session = get_active_session()

st.title(f":snowflake: Multi-Agent Sales Assistant :snowflake:")

# Initialize session state for tracking download click
if "download_clicked" not in st.session_state:
    st.session_state.download_clicked = False


## Start testing cortex analyst api call here
from typing import List, Dict, Optional
import _snowflake
from typing import List
from snowflake.core import Root

root = Root(session)
cortex_search_service = (
    root
    .databases["TR_MULTI_AGENT"]
    .schemas["PUBLIC"]
    .cortex_search_services["PRODUCT_INFO_SEARCH"]
)

class CortexAnalyst():
    def __init__(self, db: str, schema: str, stage: str, semantic_model_file_path: str):
        self.db = db
        self.schema = schema
        self.stage = stage
        self.semantic_model_file_path = semantic_model_file_path


    # @instrument
    def send_message(self, prompt: str) -> dict:

        """Calls the REST API and returns the response."""
        
        messages = []
        messages.append({"role": "user", "content": [{"type": "text", "text": prompt}]})
        request_body = {
            "messages": messages, #need to wrap in a list?
            "semantic_model_file": f"@{self.db}.{self.schema}.{self.stage}/{self.semantic_model_file_path}",
        }

        print(request_body)

        resp = _snowflake.send_snow_api_request(
            "POST",
            f"/api/v2/cortex/analyst/message",
            {},
            {},
            request_body,
            {},
            30000,
        )
        if resp["status"] < 400:
            return json.loads(resp["content"])
        else:
            # messages.pop()
            raise Exception(
                f"Failed request with status {resp['status']}: {resp}"
            )
    # @instrument
    def process_message(self, prompt: str) -> None:
        """Processes a message and adds the response to the chat."""
        messages=[]
        messages.append(
            {"role": "user", "content": [{"type": "text", "text": prompt}]}
        )
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Generating response..."):
                # response = "who had the most rec yards week 10"
                response = self.send_message(prompt=prompt)
                request_id = response["request_id"]
                content = response["message"]["content"]
                messages.append(
                    {**response['message'], "request_id": request_id}
                )
        return self.display_content(content=content, request_id=request_id, prompt = prompt)  # type: ignore[arg-type]
        # return response
    
    # @instrument
    def display_content(self,
        content: List[Dict[str, str]],
        request_id: Optional[str] = None,
        message_index: Optional[int] = None,
        prompt: Optional[str] = None,
    ) -> None:
        """Displays a content item for a message."""
        message_index = message_index or len(prompt)
        # if request_id:
            # with st.expander("Request ID", expanded=False):
                # st.markdown(request_id)
        for item in content:
            if item["type"] == "text":
                st.markdown(item["text"])
            elif item["type"] == "suggestions":
                with st.expander("Suggestions", expanded=True):
                    for suggestion_index, suggestion in enumerate(item["suggestions"]):
                        if st.button(suggestion, key=f"{message_index}_{suggestion_index}"):
                            st.session_state.active_suggestion = suggestion
            elif item["type"] == "sql":
                return self.display_sql(item["statement"])

    # @instrument
    def display_sql(self, sql: str) -> None:
        with st.expander("SQL Query", expanded=False):
            st.code(sql, language="sql")
        with st.expander("Results", expanded=True):
            with st.spinner("Running SQL..."):
                session = get_active_session()
                df = session.sql(sql).to_pandas()
                if len(df.index) > 1:
                    data_tab, line_tab, bar_tab = st.tabs(
                        ["Data", "Line Chart", "Bar Chart"]
                    )
                    data_tab.dataframe(df)
                    if len(df.columns) > 1:
                        df = df.set_index(df.columns[0])
                    with line_tab:
                        st.line_chart(df)
                    with bar_tab:
                        st.bar_chart(df)
                else:
                    st.dataframe(df)

        return df

CA = CortexAnalyst(db='TR_MULTI_AGENT', schema='PUBLIC', stage='SEMANTIC', semantic_model_file_path='customer_data.yaml')

from snowflake.cortex import complete 
from snowflake.cortex import complete 

class Multi_Agent_App:

    # def __init__(self):

    def retrieval_handler (self, client: str) -> dict:
        
        # Use sql to get list of currently used products and propensity-model-suggested product
        products_used = session.sql(f"SELECT PRODUCTS_USED FROM CUSTOMER_DATA WHERE CUSTOMER= '{client}'").collect()[0][0]
        suggested_product = session.sql(f"SELECT PROPENSITY_MODEL_SUGGESTED_PRODUCT FROM CUSTOMER_DATA WHERE CUSTOMER= '{client}'").collect()[0][0]

        #retrieve the summaries and make a summary of summaries
        conversation_summaries = session.sql(f"SELECT DATE, NAME, TITLE, SUMMARY FROM CUSTOMER_CONVERSATIONS WHERE CUSTOMER = '{client}'").collect()

        # Format conversation summaries as text
        conv_text = "\n".join([f"{row['DATE']} - {row['NAME']} ({row['TITLE']}): {row['SUMMARY']}" for row in conversation_summaries])
    
        #create summary of summaries
        client_history_prompt = f"You are an expert sales trainer. Write an actionable summary of the past sales conversations based on \
        our intention to sell {suggested_product}. Keep it brief. \
        Here are the past conversations: {conv_text}"
        
        client_history_summary = complete("claude-3-5-sonnet", client_history_prompt)

        #Retrieve relevant docuemntation for this product
        prompt = f"Retrieve relevant documentation for {suggested_product}"
        root = Root(session)
        cortex_search_service = (
            root
            .databases["TR_MULTI_AGENT"]
            .schemas["PUBLIC"]
            .cortex_search_services["PRODUCT_INFO_SEARCH"]
        )
        resp = cortex_search_service.search(
            query=prompt,
            columns=["SEARCH_COL"],
            limit=5)
    
        product_chunks = [row["SEARCH_COL"] for row in resp.results] if resp.results else []
        
        #Pass document chunks to LLM to get a product value prop for suggested product
        LLM_prompt = f"Generate a concise summary of the product benefits, value props, and a customer reference for product - {suggested_product} \
                        using the following contextual information - {product_chunks}"
        product_value_prop = complete("claude-3-5-sonnet", LLM_prompt)

        return {
            "products_used": products_used,
            "suggested_product": suggested_product,
            "product_value_prop": product_value_prop,
            "client_history_summary": client_history_summary,
            
        }
        

    def agent_1_product_info(self, client: str, client_history_summary: Optional[str]) -> str:
        """
        takes client and inserts into predefined prompt and passes to cortex analyst to return list of products client uses today
        """
        # resp = CA.process_message(f"What products are being used by our client {client}")
        # products_used = resp.iloc[:,0].to_list()

        products_used = session.sql(f"SELECT PRODUCTS_USED FROM CUSTOMER_DATA WHERE CUSTOMER= '{client}'").collect()[0][0]
        suggested_product = session.sql(f"SELECT PROPENSITY_MODEL_SUGGESTED_PRODUCT FROM CUSTOMER_DATA WHERE CUSTOMER= '{client}'").collect()[0][0]

        agent_1_response = f'''The following products are used by {client} - {products_used} \n\n
        
        \n Our propensity model has suggested the following product - SUGGESTED PRODUCT: **{suggested_product}** \n\n
        
        {client_history_summary}
        
        '''

        return agent_1_response

    def agent_2_client_web_search(self, client: str, suggested_product: Optional[str]) -> list:
        """ 
        calls api to google client name and return top three news articles. 
        Potentially use bs4 or similar library to parse web results
        Return list of web page text (or potentially pass to LLM to generate summary)
        """

        # api_key = os.environ.get("GOOGLE_API_KEY")
        # cse_id = os.environ.get("GOOGLE_CSE_ID")

        # web_query = f"top news for {client}"
        # url = "https://www.googleapis.com/customsearch/v1"
        # params = {
        #     "key": api_key,
        #     "cx": cse_id,
        #     "q": web_query,
        #     "num": 3
        # }

        # top_3_results = requests.get(url, params=params)

        # news_summary_list = []

        # for result in top_3_result:
        #     news_summaries_list.append(complete('snowflake-llama-3.3-70b', f'summarize the following web page {result}'))

        # return news_summaries_list

        if suggested_product is None:
            suggested_product = self.retrieval_handler(client)['suggested_product']
        news_summaries_list = []
        news_summaries_list.append(complete('snowflake-llama-3.3-70b', f'generate a brief news summary for client {client}. \
        It can be fictious but should be within the realm of what that client actually does. \
        Start the summary with a key highlight based on what in the news relates specifically to selling Snowflake\'s\
        {suggested_product} product'))
        
        return news_summaries_list


    def agent_3_market_web_search(self, client: str) -> list:
        """ 
        uses an llm to determine client industry, then ues api to google client industry and return top three articles. 
        Potentially use bs4 or similar library to parse web results
        Return list of web page text (or potentially pass to LLM to generate summary)
        """
        # api_key = os.environ.get("GOOGLE_API_KEY")
        # cse_id = os.environ.get("GOOGLE_CSE_ID")

        # client_market = complete('snowflake-llama-3.3-70b', f'what is the most applicable market for the company {client}')

        # web_query = f"market news for {client_market}"
        # url = "https://www.googleapis.com/customsearch/v1"
        # params = {
        #     "key": api_key,
        #     "cx": cse_id,
        #     "q": web_query,
        #     "num": 3
        # }

        # top_3_results = requests.get(url, params=params)

        # market_news_summary_list = []

        # for result in top_3_result:
        #     market_news_summary_list.append(complete('snowflake-llama-3.3-70b', f'summarize the following web page {result}'))
        market_news_summaries_list = []
        market_news_summaries_list.append(complete('snowflake-llama-3.3-70b', f'generate a brief market research analysis for the market that\
        your client {client} operates in. Focus on areas of their market that relate to what Snowflake can help with \
        It can be fictious but should be within the realm of how that market actually operates. \
        If it is not a known client/market you can just assume the client operates in the information technology market'))
        return market_news_summaries_list

    def agent_4_prep_pitch(self, client: str, product_info: Optional[str], client_news: Optional[list], market_news: Optional[list], client_history_summary: Optional[str]) -> str:
        """ 
        passes products, client news, and market news to an LLM to come up with a rough prep pitch

        """
        

        if product_info is None:
            product_info = self.agent_1_product_info(client, client_history_summary)
        if client_news is None:
            client_news = self.agent_2_client_web_search(client, suggested_product)
        if market_news is None:
            market_news = self.agent_3_market_web_search(client)
        prep_pitch = complete('snowflake-llama-3.3-70b', 
                              f"""
                              prepare a product pitch for ONLY FOR THE SUGGESTED PRODUCT based on the following product info and the client and market news 
                              past_history: {client_history_summary}
                              product_advantages: {product_info}
                              client_news: {client_news}
                              market_news: {market_news}
                              """)
        return prep_pitch
    
    def agent_5_disco_questions(self, client: str, product_info: Optional[str], pitch: Optional[str], client_news: Optional[list], market_news: Optional[list], client_history_summary: Optional[str]) -> str:
        """ 
        passes products, client news, and market news to an LLM to come up with a list of appropriate discovery questions
        """
        
        if product_info is None:
            product_info = self.agent_1_product_info(client, client_history_summary)
        if client_news is None:
            client_news = self.agent_2_client_web_search(client, suggested_product)
        if market_news is None:
            market_news = self.agent_3_market_web_search(client)
        disco_questions = complete('snowflake-llama-3.3-70b', 
                              f"""
                              You are an expert sales trainer. Prepare the 5 most important discovery questions\
                              that the sales rep should ask in the client meeting for the SUGGESTED PRODUCT given the pitch plan to the client and market news
                              pitch: {pitch}
                              past_history: {client_history_summary}
                              product_info: {product_info}
                              client_news: {client_news}
                              market_news: {market_news}
                              """)
        return disco_questions


    def orchestrate_all_agents(self, client: str, output_file_name: str):
        """ 
        primary function that ties all agents together and writes out a final markdown file with all prep materials
        """
        st.write("Starting Sales Prep Agent Pipeline...")

        conversation_summary = self.retrieval_handler(client)

        product_info = self.agent_1_product_info(client, conversation_summary["product_value_prop"])
        st.write(product_info)
        
        client_history = self.agent_1_product_info(client, conversation_summary["client_history_summary"])
        st.write(client_history)
        
        client_news = self.agent_2_client_web_search(client, conversation_summary["suggested_product"] )
        st.write(', '.join(client_news))

        market_news = self.agent_3_market_web_search(client)
        st.write(', '.join(market_news))

        pitch = self.agent_4_prep_pitch(client, product_info, client_news, market_news, conversation_summary["client_history_summary"])
        st.write(pitch)
        
        disco_questions = self.agent_5_disco_questions(client, pitch, product_info, client_news, market_news, conversation_summary["client_history_summary"])
        st.write(disco_questions)
        
        markdown_doc = f"# Prep Report for Client **{client}**" + \
                       "\n\n ## Product Info \n\n" + product_info + \
                        "\n\n ## Client History \n\n" + client_history + \
                       "\n\n ## Client News \n\n " + ' '.join(client_news)+ \
                       "\n\n ## Market News \n\n " + ' '.join(market_news) + \
                       "\n\n ## Proposed Pitch \n\n " + pitch + \
                       "\n\n ## Discovery Questions \n\n  " + disco_questions + \
                       "\n\n # END OF DOCUMENT - good luck with your meeting :)"

        with open(output_file_name, "wb") as f:
            f.write(markdown_doc.encode("utf-8"))

        st.write(f"Client prep file written to {output_file_name}!")

        return markdown_doc

MULTI_AGENT = Multi_Agent_App()

if user_input := st.chat_input("Who is your client?"):
    output_file_name = f"{user_input.replace(' ', '')}_prep_file.md"
    multi_agent_output = MULTI_AGENT.orchestrate_all_agents(user_input, output_file_name)


    download_button = st.download_button(f'Download {user_input} Prep Report', open(output_file_name, 'rb'), 
                                         file_name=output_file_name, use_container_width=True)
    # if download_button:
    #    st.session_state.download_clicked = True  # Set flag in session state
    #    if st.session_state.download_clicked:
    st.success("✅ Prep File Ready!")
