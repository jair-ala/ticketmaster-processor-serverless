import boto3
import pandas as pd
import os
import io
import pymongo
import certifi

mongo_client = pymongo.MongoClient(os.environ.get('MONGODB_URI_PRODUCT'),tlsCAFile=certifi.where())
db = mongo_client['product-db']
forthcomingProduct_collection = db['forthcomingProduct']
product_collection = db['product']

s3_client = boto3.client('s3')

def lambda_handler(event, context):
    bucket_name = event['Records'][0]['s3']['bucket']['name']
    file_name = event['Records'][0]['s3']['object']['key']
    print(f'process=handler, status=started, bucket_name={bucket_name}, file_name={file_name}')

    try:
        obj = s3_client.get_object(Bucket=bucket_name, Key=file_name)
        csv_content = obj['Body'].read().decode('utf-8')
        
        df = pd.read_csv(io.StringIO(csv_content))
        
        ocesa_df = df[df['PROMOTER_ID'].astype(str).str.contains(r'\b304\b', regex=True)]

        print(f'process=handler, status=processing, original_df={df.shape}, ocesa_df={ocesa_df.shape}')

        # Filter out only the attributes that are required
        selected_fields_df = ocesa_df[['ATTRACTION_ID', 'ATTRACTION_NAME', 'EVENT_ID', 'EVENT_NAME', 'VENUE_NAME', 'EVENT_START_LOCAL_DATE']]
        
        # Convert to Date for mongo
        selected_fields_df['EVENT_START_LOCAL_DATE'] = pd.to_datetime(selected_fields_df['EVENT_START_LOCAL_DATE'], errors='coerce')
        
        # Add CREATED_AT column
        selected_fields_df['CREATED_AT'] = pd.Timestamp.now()

        # Fetch products already uploaded
        product_attraction_ids, product_event_ids = fetch_products()

        # Discard records from selected_fields that match ATTRACTION_ID or EVENT_ID in products
        filtered_selected_fields_df = selected_fields_df[
            ~selected_fields_df['ATTRACTION_ID'].isin(product_attraction_ids) &
            ~selected_fields_df['EVENT_ID'].isin(product_event_ids)
        ]

        filtered_selected_fields_df.columns = ['attractionId', 'attractionName', 'eventId', 
                                               'eventName', 'venueName', 'eventStartLocalDate', 'createdAt']
        records_to_insert = filtered_selected_fields_df.to_dict(orient='records')
        insert_products(records_to_insert)

    except Exception as e:
        print(f'process=handler, status=error, error={str(e)}')
    
    print(f'process=handler, status=finished, bucket_name={bucket_name}, file_name={file_name}')


def fetch_products():
    print(f'process=fetch_products_from_db, status=started')
    query = {
        "seller": "TICKET_MASTER",
        "status": {"$in": ["ACTIVE", "INACTIVE"]}
    }
    products = list(product_collection.find(query, {
        "metadata.ATTRACTIONID": 1,
        "metadata.TICKETMASTEREVENTID": 1,
    }))

    # Extract the IDs into sets
    product_attraction_ids = set()
    product_event_ids = set()
    
    for p in products:
        try:
            product_attraction_ids.add(p['metadata']['ATTRACTIONID'])
            product_event_ids.add(p['metadata']['TICKETMASTEREVENTID'])
        except Exception as e:
            print(f"""process=fetch_products_from_db, status=warning, 
                  product={p},msg={str(e)}""")

    print(f'process=fetch_products_from_db, status=processing, total_products={len(products)}')
    return product_attraction_ids, product_event_ids
    

def insert_products(records):
    # First of all delete all records
    forthcomingProduct_collection.delete_many({})
    print(f'process=insert_products, status=started, total_records={len(records)}')
    forthcomingProduct_collection.insert_many(records)
    print(f'process=insert_products, status=finished, total_records={len(records)}')