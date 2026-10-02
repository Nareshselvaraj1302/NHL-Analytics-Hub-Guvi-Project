import streamlit as st
import mysql.connector
import pandas as pd

connection = mysql.connector.connect(
    host='localhost',
    port=3306,
    database='NHL_ANALYTICS_PROJECT',
    user='root',
    password="Omsivaya@20"
)
cursor = connection.cursor()

from streamlit_option_menu import option_menu
st.title("This is a title")
st.title("_Streamlit_ is :blue[cool] :sunglasses:")
st.title("Dashboard", icon=":material/dashboard:")
with st.sidebar:
    selected = option_menu("Main Menu", ["Home","Teams","Queries",'Settings'], 
        icons=['house', 'gear'], menu_icon="cast", default_index=1)
    selected

if selected == "Home":
        c1,c2,c3 = st.columns(3)
        with c1:
            st.image('/Users/nareshselvaraj/pandas course/NHL Analytics Hub Guvi Project/hockey.jpg', width=200)
        with c2:
            st.write("Welcome to the NHL Analytics HUB!")

        cursor.execute("select count(*) from teams")
        total_teams = cursor.fetchone()[0]
        st.metric("Total Teams", total_teams)
           
if selected == "Queries":
    st.write("This is the Quries Page")
    option = st.selectbox(
         "Select a query to run",
         ("1.Show all teams", "2.Show All players", "3.Show All Games"),
)
    
    if option == "1.Show all teams":
           df = pd.read_sql_query("select * from teams", connection)
           st.dataframe(df)
    elif option == "2.Show All players":
               df = pd.read_sql_query("select team_abbrev from teams", connection)
               st.dataframe(df)
    elif option == "3.Show All Games":
                df = pd.read_sql_query("select * from teams", connection)
                st.dataframe(df)
      
 




