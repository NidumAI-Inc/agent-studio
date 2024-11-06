from app.db.databases import *
from threading import Semaphore, Thread
import os
import uuid
import tempfile
import shutil
from datetime import datetime
import subprocess

import subprocess

def run_command_sync(cmd):
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode != 0:
            raise Exception(f"Command failed with exit code {result.returncode}: {result.stderr}")
        return result.stdout
    except Exception as e:
        raise Exception(f"Failed to run command: {cmd} -> {e}")
def normalize_phone_number(phone_number: str) -> str:
    """
    Normalize phone numbers by ensuring they include the '+' sign, 
    and removing spaces or special characters.
    """
    phone_number = phone_number.strip().replace(' ', '').replace('-', '')
    if not phone_number.startswith('+'):
        phone_number = '+' + phone_number
    return phone_number

# Process the calls in the background
def process_campaign_calls_sync(campaign_id: str, email: str):
    """
    Process campaign calls by starting outbound calls for each phone number in the campaign.
    Ensure phone number normalization to match the format in the logs collection.
    """
    db = get_database()
    campaign = db.campaigns.find_one({"campaign_id": campaign_id, "email": email})
    
    if not campaign:
        print(f"Campaign not found: {campaign_id}")
        return

    # Normalize the agent phone number
    agent_phone_number = normalize_phone_number(campaign['agent_phone_number'])
    
    # Retrieve the outbound_trunk_id from the logs collection using normalized phone number
    log_entry = db.logs.find_one({"email": email, "phone_number": agent_phone_number})
    if not log_entry:
        print(f"No trunk entry found for email: {email}, agent_phone_number: {agent_phone_number}")
        db.campaigns.update_one(
            {"campaign_id": campaign_id},
            {"$set": {"status": "failed", "updated_at": datetime.utcnow()}}
        )
        return

    outbound_trunk_id = log_entry.get('outbound_trunk_id')
    if not outbound_trunk_id:
        print(f"No outbound_trunk_id found for email: {email}, agent_phone_number: {agent_phone_number}")
        db.campaigns.update_one(
            {"campaign_id": campaign_id},
            {"$set": {"status": "failed", "updated_at": datetime.utcnow()}}
        )
        return

    phone_numbers = campaign.get('phone_numbers', [])
    if not phone_numbers:
        print(f"No phone numbers found for campaign {campaign_id}")
        db.campaigns.update_one(
            {"campaign_id": campaign_id},
            {"$set": {"status": "no_numbers", "updated_at": datetime.utcnow()}}
        )
        return

    # Update campaign status to 'running'
    db.campaigns.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"status": "running", "updated_at": datetime.utcnow()}}
    )

    called_numbers = campaign.get('called_numbers', [])
    remaining_numbers = [num for num in phone_numbers if num not in called_numbers]

    # Semaphore to limit the number of concurrent calls
    semaphore = Semaphore(3)

    def make_call(phone_number):
        with semaphore:
            try:
                print(f"Initiating call to {phone_number}")

                participant_identity = f"sip_{phone_number.strip('+')}_{campaign_id}_outbound"
                room_name = f"call-{phone_number.strip('+')}"
                participant_name = "Campaign Call"

                # JSON content for SIP participant creation
                sip_participant_content = f"""
                {{
                    "sip_trunk_id": "{outbound_trunk_id}",
                    "sip_call_to": "{phone_number}",
                    "room_name": "{room_name}",
                    "participant_identity": "{participant_identity}",
                    "participant_name": "{participant_name}"
                }}
                """

                temp_dir = tempfile.mkdtemp()
                sip_participant_filename = f"sipParticipant_{uuid.uuid4()}.json"
                sip_participant_path = os.path.join(temp_dir, sip_participant_filename)

                # Write the JSON content to a file
                with open(sip_participant_path, "w") as f:
                    f.write(sip_participant_content)

                # Execute the lk command using run_command_sync function
                create_sip_participant_cmd = f"lk sip participant create {sip_participant_path}"
                print(f"Running command: {create_sip_participant_cmd}")

                command_output = run_command_sync(create_sip_participant_cmd)
                print(f"Command output: {command_output}")

                # Update the campaign with the called number
                db.campaigns.update_one(
                    {"campaign_id": campaign_id},
                    {"$addToSet": {"called_numbers": phone_number}}
                )

            except Exception as e:
                print(f"Error making call to {phone_number}: {e}")

            finally:
                shutil.rmtree(temp_dir)

    # Start the calls concurrently using threads
    threads = []
    for phone_number in remaining_numbers:
        t = Thread(target=make_call, args=(normalize_phone_number(phone_number),))
        threads.append(t)
        t.start()

    # Wait for all threads to complete
    for t in threads:
        t.join()

    # Update campaign status to 'completed' after all calls are made
    db.campaigns.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"status": "completed", "updated_at": datetime.utcnow()}}
    )
    print(f"Campaign {campaign_id} completed successfully.")
