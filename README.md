
<div style="text-align: center;">
 <h1>LLM CHATBOT API</h1>
</div>

---
![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54) ![Shell Script](https://img.shields.io/badge/shell_script-%23121011.svg?style=for-the-badge&logo=gnu-bash&logoColor=white)
![Anaconda](https://img.shields.io/badge/Anaconda-%2344A833.svg?style=for-the-badge&logo=anaconda&logoColor=white) ![Flask](https://img.shields.io/badge/flask-%23000.svg?style=for-the-badge&logo=flask&logoColor=white) ![Keras](https://img.shields.io/badge/Keras-%23D00000.svg?style=for-the-badge&logo=Keras&logoColor=white) ![Matplotlib](https://img.shields.io/badge/Matplotlib-%23ffffff.svg?style=for-the-badge&logo=Matplotlib&logoColor=black) ![NumPy](https://img.shields.io/badge/numpy-%23013243.svg?style=for-the-badge&logo=numpy&logoColor=white) ![Pandas](https://img.shields.io/badge/pandas-%23150458.svg?style=for-the-badge&logo=pandas&logoColor=white)
![Cent OS](https://img.shields.io/badge/cent%20os-002260?style=for-the-badge&logo=centos&logoColor=F0F0F0)  ![Ubuntu](https://img.shields.io/badge/Ubuntu-E95420?style=for-the-badge&logo=ubuntu&logoColor=white) ![NeoVim](https://img.shields.io/badge/NeoVim-%2357A143.svg?&style=for-the-badge&logo=neovim&logoColor=white) ![VIM](https://img.shields.io/badge/VIM-%2311AB00.svg?&style=for-the-badge&logo=vim&logoColor=white) ![VScode](https://img.shields.io/badge/Visual_Studio_Code-0078D4?style=for-the-badge&logo=visual%20studio%20code&logoColor=white) ![Notepad++](https://img.shields.io/badge/Notepad++-90E59A.svg?style=for-the-badge&logo=notepad%2B%2B&logoColor=black)
---

<div style="text-align: center;">

</div>
<div>
    <h3 style="text-align: center;"><strong>Large Language Model<br/></strong>
        <strong>based in <span style="color: #203072;" data-color-group="turquoise">inspiration</span>
        </strong>
    </h3>
    <p>The Large Language Model is inspired by the opensource community of hugging face.</p>
    <p>The model we will make use is LLM you can find on Hugging preferable text-to-text models, and it makes use of kafka.
    <ol>
        <li>flask api</li>
        <li>websockets</li>
        <li>msbot</li>
        <li>vosk</li>
        <li>confluent-kafka</li>
    </ol>
</div>


## Setup Environment

1. install Pre-commit

    ```bash
    pip install pre-commit
    ```

    **NB**: Install pre-commit globally not in virtual env

2. Install pre-commit hooks

    ```bash
    pre-commit install
    ```

3. Create Virtual Environment
   * **Command Prompt (cmd):**
   ```commandline
   python -m venv dev
   dev\Scripts\activate
   ```

   * **PowerShell:**
   ```commandline
   python -m venv dev
   dev\Scripts\Activate.ps1
   ```

   * **Linux/Unix:**
   ```bash
   python -m venv dev
   source dev/bin/activate
   ```

4. Create .env file

    Generate and .env file and user default values found in .exampl.env file or customize the values to your liking if you are using different kafka running form dedicated host and if you desire to use you own llm from hugging face.

    **NB:** Please not for now we don't support kafka which requires authentication

## How to Run Different Applications

1. Install Requirements

    ```bash
    pip install -r requirements-plain.txt
    ```

    Then install [Pytorch](https://pytorch.org/)

    * **Install Pytorch with CUDA 12.4**

    ```bash
    pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
    ```

    * **Install Pytorch with CUDA 12.1**

    ```bash
    pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
    ```

    * **Install Pytorch with CUDA 11.8**

    ```bash
    pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
    ```

    * **Install Pytorch with CPU**

    ```bash
    pip3 install torch torchvision torchaudio
    ```

2. To run flask API

    ```bash
    python bot.py
    ```

3. To run Websockets

    ```bash
    python websocket.py
    ```

4. To run MS bot

    ```bash
    python mschatbot\app.py
    ```

5. To Run Audio Transcriber

    ```bash
    python vttllm\main.py
    ```

6. Run LLM Server

    ```bash
    python llm_run_server.py
    ```

## Containerization

1. Build Container image for llm server
    * **Using Docker**
    ```bash
    docker build -f LLM.Dockerfile -t <registory>/llm-server:latest .
    ```

    * **Using Podman**
    ```bash
    podman build -f LLM.Dockerfile -t <registory>/llm-server:latest .
    ```

    * **Run Container**
    ```bash
    docker-compose up .
    ```

### Contact Me

![Developer](/img/developer_shape.png)

**Email :** [Developer](mailto:prince@developer.co.zw)

**WhatsApp/Mobile :** [+27783442644](tel:+27783442644)
