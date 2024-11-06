from pymongo import MongoClient, errors

mongo_user = "aj"
mongo_password = "kesavan12"
mongo_host = "haive.v5q7m.mongodb.net"
database_name = "voice_ai_app_db"

def get_database():
    # Construct the MongoDB connection string
    connection_string = f"mongodb+srv://{mongo_user}:{mongo_password}@{mongo_host}/?retryWrites=true&w=majority"
    
    try:
        # Establish a connection to MongoDB
        client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
        # Ping the database to check if the connection is successful
        client.admin.command('ping')
        return client[database_name]
    except errors.ConfigurationError as config_error:
        print(f"MongoDB Configuration Error: {config_error}")
        raise
    except errors.ServerSelectionTimeoutError as timeout_error:
        print(f"MongoDB Connection Timeout: {timeout_error}")
        raise
