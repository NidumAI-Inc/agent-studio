### LiveKit Server Setup Guide**

This guide will help you set up the LiveKit Server for Agent Studio. LiveKit is a key component that enables real-time audio communication.

#### **Step 1: Install Go on the Server**

1. **Download the Go Binary**:
    - Visit the official Go downloads page [here](https://golang.org/dl/).
    - Copy the link for the Linux version (e.g., `go1.23.0.linux-amd64.tar.gz`).

2. **Use curl to download the Go binary**:

    ```bash
    curl -O https://go.dev/dl/go1.23.0.linux-amd64.tar.gz
    ```

3. **Remove any previous Go installation**:

    ```bash
    sudo rm -rf /usr/local/go
    ```

4. **Extract the Go archive to `/usr/local/`**:

    ```bash
    sudo tar -C /usr/local -xzf go1.23.0.linux-amd64.tar.gz
    ```

5. **Add Go to the PATH environment variable**:

    ```bash
    echo 'export PATH=$PATH:/usr/local/go/bin' | sudo tee -a /etc/profile
    source /etc/profile
    ```

6. **Verify the Go installation**:

    ```bash
    go version
    ```

7. **Set up the Go environment**:

    ```bash
    mkdir -p /root/go/bin
    export GOPATH=/root/go
    export PATH=$PATH:/root/go/bin
    ```

8. **Persist the changes**:

    ```bash
    echo 'export GOPATH=/root/go' >> ~/.bashrc
    echo 'export PATH=$PATH:/root/go/bin' >> ~/.bashrc
    source ~/.bashrc
    ```

#### **Step 2: Clone the LiveKit Repository and Set Up Environment**

1. **Clone the LiveKit repository**:

    ```bash
    git clone https://github.com/livekit/livekit.git
    cd livekit
    ```

2. **Run the bootstrap script**:

    ```bash
    ./bootstrap.sh
    ```

3. **Install Mage (Go-based build tool)**:

    ```bash
    go install github.com/magefile/mage@latest
    ```

4. **Verify the installation of `mage`**:

    ```bash
    ls $HOME/go/bin
    ```

5. **Add Go Bin to PATH**:

    ```bash
    export PATH=$PATH:$HOME/go/bin
    echo 'export PATH=$PATH:$HOME/go/bin' >> ~/.bashrc
    source ~/.bashrc
    ```

6. **Build the project using Mage**:

    ```bash
    mage
    ```

#### **Step 3: Build LiveKit CLI from Source**

1. **Install Git LFS**:

    - Install Git LFS from the [Git LFS installation guide](https://git-lfs.github.com/).

2. **Initialize Git LFS**:

    ```bash
    git lfs install
    ```

3. **Clone the LiveKit CLI repository**:

    ```bash
    git clone https://github.com/livekit/livekit-cli.git
    cd livekit-cli
    ```

4. **Build and install the LiveKit CLI**:

    ```bash
    make install
    ```

5. **Verify the installation**:

    ```bash
    lk --help
    ```

#### **Step 4: Install, Configure, and Run Redis on Ubuntu**

1. **Update package lists**:

    ```bash
    sudo apt update
    ```

2. **Install Redis**:

    ```bash
    sudo apt install redis-server -y
    ```

3. **Set `supervised` to `systemd` in Redis configuration**:

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

6. **Test Redis**:

    ```bash
    redis-cli ping
    ```

#### **Step 5: Start LiveKit Server**

1. **Run the LiveKit server**:

    ```bash
    ./livekit-server --redis-host 127.0.0.1:6379 --dev
    ```

#### **LiveKit Server Troubleshooting**

- **Redis Issues**: Ensure Redis is running and accessible (`redis-cli ping`).
- **Environment Variables**: Confirm all environment variables are set correctly.
- **Server Logs**: Use debug mode for more detailed logs:
    ```bash
    ./livekit-server --dev --debug
    ```

