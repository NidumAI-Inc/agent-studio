from setuptools import setup, find_packages

setup(
    name='aistudio',
    version='1.0.0',
    description='A voice assistant AI app using Livekit, LLaMA, and OpenAI integrations',
    author='nidum',
    author_email='info@nidum.ai',
    python_requires='>=3.12',
    install_requires=[
        'aiodns==3.2.0',
        'aiofile==3.8.8',
        'aiohappyeyeballs==2.4.0',
        'aiohttp==3.10.5',
        'aiosignal==1.3.1',
        'annotated-types==0.7.0',
        'annoy==1.17.3',
        'anyio==4.4.0',
        'attrs==24.2.0',
        'av==13.0.0',
        'beautifulsoup4==4.12.3',
        'caio==0.9.17',
        'certifi==2024.8.30',
        'cffi==1.17.1',
        'charset-normalizer==3.3.2',
        'click==8.1.7',
        'coloredlogs==15.0.1',
        'dataclasses-json==0.6.7',
        'Deprecated==1.2.14',
        'dirtyjson==1.0.8',
        'distro==1.9.0',
        'dnspython==2.6.1',
        'fastapi==0.114.2',
        'flatbuffers==24.3.25',
        'frozenlist==1.4.1',
        'fsspec==2024.9.0',
        'greenlet==3.1.0',
        'h11==0.14.0',
        'httpcore==1.0.5',
        'httpx==0.27.2',
        'humanfriendly==10.0',
        'idna==3.9',
        'jiter==0.5.0',
        'joblib==1.4.2',
        'livekit==0.16.2',
        'livekit-agents==0.8.12',
        'livekit-api==0.7.0',
        'livekit-plugins-deepgram==0.6.7',
        'livekit-plugins-openai==0.8.3',
        'livekit-plugins-rag==0.2.2',
        'livekit-plugins-silero==0.6.4',
        'livekit-protocol==0.6.0',
        'llama-cloud==0.0.17',
        'llama-index==0.11.9',
        'llama-index-agent-openai==0.3.1',
        'llama-index-cli==0.3.1',
        'llama-index-core==0.11.9',
        'llama-index-embeddings-openai==0.2.5',
        'llama-index-indices-managed-llama-cloud==0.3.1',
        'llama-index-legacy==0.9.48.post3',
        'llama-index-llms-openai==0.2.7',
        'llama-index-multi-modal-llms-openai==0.2.1',
        'llama-index-program-openai==0.2.0',
        'llama-index-question-gen-openai==0.2.0',
        'llama-index-readers-file==0.2.1',
        'llama-index-readers-llama-parse==0.3.0',
        'llama-parse==0.5.5',
        'lxml==5.3.0',
        'marshmallow==3.22.0',
        'mpmath==1.3.0',
        'multidict==6.1.0',
        'mypy-extensions==1.0.0',
        'nest-asyncio==1.6.0',
        'networkx==3.3',
        'nltk==3.9.1',
        'numpy==1.26.4',
        'onnxruntime==1.19.2',
        'openai==1.45.0',
        'packaging==24.1',
        'pandas==2.2.2',
        'pillow==10.3.0',
        'protobuf==5.28.1',
        'psutil==5.9.8',
        'pycares==4.4.0',
        'pycparser==2.22',
        'pydantic==2.9.1',
        'pydantic_core==2.23.3',
        'PyJWT==2.9.0',
        'pymongo==4.8.0',
        'pypdf==4.3.1',
        'PyPDF2==3.0.1',
        'python-dateutil==2.9.0.post0',
        'python-docx==1.1.2',
        'python-dotenv==1.0.1',
        'python-multipart==0.0.9',
        'pytz==2024.2',
        'PyYAML==6.0.2',
        'regex==2024.9.11',
        'requests==2.32.3',
        'setuptools==74.1.2',
        'six==1.16.0',
        'sniffio==1.3.1',
        'soupsieve==2.6',
        'SQLAlchemy==2.0.34',
        'starlette==0.38.5',
        'striprtf==0.0.26',
        'sympy==1.13.2',
        'tenacity==8.5.0',
        'tiktoken==0.7.0',
        'tqdm==4.66.5',
        'types-protobuf==4.25.0.20240417',
        'typing-inspect==0.9.0',
        'typing_extensions==4.12.2',
        'tzdata==2024.1',
        'urllib3==2.2.3',
        'uvicorn==0.30.6',
        'watchfiles==0.24.0',
        'wrapt==1.16.0',
        'yarl==1.11.1',
        'marshmallow==3.22.0',
        'mpmath==1.3.0',
        'multidict==6.1.0',
        'mypy-extensions==1.0.0',
        'nest-asyncio==1.6.0',
        'networkx==3.3',
        'nltk==3.9.1',
        'numpy==1.26.4',
        'onnxruntime==1.19.2',
        'openai==1.45.0',
        'packaging==24.1',
        'pandas==2.2.2',
        'pillow==10.3.0',
        'protobuf==5.28.1',
        'psutil==5.9.8',
        'pycares==4.4.0',
        'pycparser==2.22',
        'pydantic==2.9.1',
        'pydantic_core==2.23.3',
        'PyJWT==2.9.0',
        'pymongo==4.8.0',
        'pypdf==4.3.1',
        'PyPDF2==3.0.1',
        'python-dateutil==2.9.0.post0',
        'python-docx==1.1.2',
        'python-dotenv==1.0.1',
        'python-multipart==0.0.9',
        'pytz==2024.2',
        'PyYAML==6.0.2',
        'regex==2024.9.11',
        'requests==2.32.3',
        'setuptools==74.1.2',
        'six==1.16.0',
        'sniffio==1.3.1',
        'soupsieve==2.6',
        'SQLAlchemy==2.0.34',
        'starlette==0.38.5',
        'striprtf==0.0.26',
        'sympy==1.13.2',
        'tenacity==8.5.0',
        'tiktoken==0.7.0',
        'tqdm==4.66.5',
        'types-protobuf==4.25.0.20240417',
        'typing-inspect==0.9.0',
        'typing_extensions==4.12.2',
        'tzdata==2024.1',
        'urllib3==2.2.3',
        'uvicorn==0.30.6',
        'watchfiles==0.24.0',
        'wrapt==1.16.0',
        'yarl==1.11.1'
    ],
    packages=find_packages(),
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'aistudio=app.cli:main',
        ],
    },

    classifiers=[
        'Programming Language :: Python :: 3.12',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
)

