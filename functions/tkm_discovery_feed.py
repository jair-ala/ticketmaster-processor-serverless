import boto3
import requests
import os
import gzip
from io import BytesIO
from urllib.parse import urlparse

s3 = boto3.client('s3')

TICKETMASTER_API_KEY = os.getenv('TICKETMASTER_API_KEY', 'kqjWTEBgv0M38oZOZGqOsAzOAGBYATTn')
TICKETMASTER_BASE_URL = os.getenv('TICKETMASTER_BASE_URL', 'https://app.ticketmaster.com')
TICKETMASTER_URL = TICKETMASTER_BASE_URL + '/discovery-feed/v2/events'

TARGET_BUCKET_NAME = os.environ['TARGET_BUCKET_NAME']
TARGET_BUCKET_FOLDER = os.environ['TARGET_BUCKET_FOLDER']


def discovery_feed():
    return requests.get(TICKETMASTER_URL, params= {
        'apikey': TICKETMASTER_API_KEY
    }).json()


def lambda_handler(event, context):
    print(f"process=handler, status=start")
    response = discovery_feed()

    mx_country_data = response.get("countries", {}).get("MX", {})


    if not mx_country_data or "CSV" not in mx_country_data:
        msg = 'No CSV data for Mexico (MX) found in response'
        print(f"process=handler, status=error, error={msg}")
        raise ValueError(msg)
    
    csv_info = mx_country_data["CSV"]
    csv_url = csv_info["uri"]
    num_events =  csv_info["num_events"]

    print(f"process=handler, status=csv found, num_events={num_events}, csv_url={csv_url}")

    csv_response = requests.get(csv_url)
    
    if csv_response.status_code != 200:
        msg = f'Failed to download the CSV file. Status code: {csv_response.status_code}'
        print(f"process=handler, status=error, error={msg}")
        raise ValueError(msg)
    
    parsed_url = urlparse(csv_url)
    original_filename = parsed_url.path.split('/')[-1]
    csv_filename = original_filename.replace('.gz', '')

    gzipped_file = BytesIO(csv_response.content)
    with gzip.GzipFile(fileobj=gzipped_file) as uncompressed_file:
        csv_content = uncompressed_file.read()
    

    s3_key = f'{TARGET_BUCKET_FOLDER}{csv_filename}'
    s3.put_object(Bucket=TARGET_BUCKET_NAME, Key=s3_key, Body=csv_content)

    print(f"process=handler, status=finished")

