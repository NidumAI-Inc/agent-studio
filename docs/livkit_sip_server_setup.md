Here's a refined version of your document:

---

### SIP Server Setup Guide**

This guide outlines the steps to set up the **SIP Server** to enable integration with external telephony systems for real-time communication in Agent Studio.

#### **Step 1: Clone and Build the SIP Server**

1. **Clone the SIP server repository**:

    ```bash
    git clone https://github.com/livekit/sip.git
    cd sip
    ```

2. **Build the SIP server using Mage**:

    ```bash
    mage build
    ```

3. **Verify the SIP server installation** by running:

    ```bash
    sip
    ```

#### **Step 2: Install, Configure, and Run Redis on Ubuntu**

1. **Update the package lists**:

    ```bash
    sudo apt update
    ```

2. **Install Redis**:

    ```bash
    sudo apt install redis-server -y
    ```

3. **Set `supervised` mode to `systemd` in Redis configuration**:

    ```bash
    sudo sed -i 's/^supervised no/supervised systemd/' /etc/redis/redis.conf
    ```

4. **Start and enable Redis**:

    ```bash
    sudo systemctl start redis-server
    sudo systemctl enable redis-server
    ```

5. **Check Redis status**:

    ```bash
    sudo systemctl status redis-server
    ```

6. **Test Redis connection**:

    ```bash
    redis-cli ping
    ```

#### **Step 3: Configure and Run the SIP Server**

1. **Create a configuration file**:

    ```bash
    nano config.yaml
    ```

    Add the following content:

    ```yaml
    api_key: "devkey"
    api_secret: "secret"
    ws_url: ws://localhost:7880
    redis:
      address: 127.0.0.1:6379
    sip_port: 5060
    rtp_port: 10000-20000
    use_external_ip: true
    logging:
      level: debug
    ```

2. **Run the SIP server in a tmux session**:

    ```bash
    tmux new -s sipserver
    sip --config=config.yaml
    ```

    Detach from the tmux session with `Ctrl + B`, then `D`.

#### **Step 4: Determine Your SIP URI and Configure a SIP Trunk**

1. **Find your public IP address**:

    ```bash
    curl ifconfig.me
    ```

2. **Construct your SIP URI**: `sip:<public-ip-address>:5060`.

3. **Create a SIP Trunk (e.g., with Twilio)**, and set your SIP URI as the Origination SIP URI.

#### **Step 5: Configure the LiveKit CLI**

1. **Set the environment variables**:

    ```bash
    export LIVEKIT_URL="ws://0.0.0.0:7880"
    export LIVEKIT_API_KEY="devkey"
    export LIVEKIT_API_SECRET="secret"
    ```

2. **Persist the environment variables**:

    ```bash
    echo 'export LIVEKIT_URL="ws://localhost:7880"' >> ~/.bashrc
    echo 'export LIVEKIT_API_KEY="devkey"' >> ~/.bashrc
    echo 'export LIVEKIT_API_SECRET="secret"' >> ~/.bashrc
    source ~/.bashrc
    ```

#### **Step 6: Create Inbound Trunk and Dispatch Rule**

1. **Create an inbound trunk configuration**:

    ```bash
    nano inboundTrunk.json
    ```

    Add the following content:

    ```json
    {
        "trunk": {
            "name": "Demo Inbound Trunk",
            "numbers": ["+1234567890"]
        }
    }
    ```

2. **Create the inbound trunk**:

    ```bash
    lk sip inbound create inboundTrunk.json
    ```

3. **Create a dispatch rule**:

    ```bash
    nano dispatchRule.json
    ```

    Add the following content:

    ```json
    {
        "name": "Demo Dispatch Rule",
        "trunk_ids": ["<your-trunk-id>"],
        "rule": {
            "dispatchRuleDirect": {
                "roomName": "my-sip-room",
                "pin": ""
            }
        }
    }
    ```

4. **Apply the dispatch rule**:

    ```bash
    lk sip dispatch create dispatchRule.json
    ```

---

#### **SIP Server Troubleshooting**

- **Redis Issues**: Ensure Redis is running and accessible by using `redis-cli ping`.
- **Connection Issues**: Check network configurations, firewall settings, and server logs for errors.
- **Server Logs**: Enable debug mode for more detailed logs:

    ```bash
    sip --config=config.yaml --debug
    ```

Following these steps will set up a fully configured and operational SIP server integrated with LiveKit.