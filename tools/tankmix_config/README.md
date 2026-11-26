# TankMix for the RadioMaster T8L

[English](#english) · [Português](#português)

## English

TankMix adds **tank (differential) mixing** to the internal ExpressLRS module of the **RadioMaster T8L**, so you can drive a two-motor robot with one stick. The T8L has no screen for a mixer, and the ExpressLRS web UI has no tank mix, so the mix runs inside the TX module before the channels are sent. The receiver runs stock ExpressLRS.

TankMix is only for the T8L. Radios with EdgeTX or OpenTX can do this mix on the radio itself.

### What it does

- **Checks your computer** for Python, PlatformIO and Git, and tells you how to install what is missing.
- **Downloads any ExpressLRS version from 3.5.0 on**, or opens one you already have, and installs the mod in it.
- **Edits the mix**: channels, steering strength, deadbands and reverses. A live preview uses the same math as the firmware, and invalid setups are blocked before they reach the compiler.
- **Builds the T8L firmware** with your binding phrase.
- **Flashes the radio over WiFi**.
- The interface is in **English and Portuguese**.

### Requirements

| | Why |
|---|---|
| [Python](https://www.python.org/downloads/) 3.8+ | runs TankMix (on Windows, tick "Add python.exe to PATH") |
| [PlatformIO Core](https://docs.platformio.org/en/latest/core/installation/methods/installer-script.html) | builds the firmware |
| [Git](https://git-scm.com/downloads) | downloads ExpressLRS and its hardware layouts |
| Internet | first build of each version, and downloading versions |

### Use

1. Unzip the release and open the `TankMix` folder.
2. Start TankMix:
   - **Windows:** double-click `TankMix.bat`.
   - **macOS:** double-click `TankMix.command`. The first time, right-click it and choose **Open**.
   - **Linux:** run `./tankmix.sh`.
3. The browser opens. Fix anything red in **System check**.
4. Under **ExpressLRS folder**, download a version, or type the path of one you have and click **Open**. If the mod is not there, click **Install tank mix**.
5. Set up the mix and click **Build firmware**.
6. On the radio, go to ExpressLRS Lua → **WiFi Connectivity** → **Enable WiFi**. Connect the computer to the radio's WiFi network and click **Flash to radio**.

Bench test before driving. Set the receiver failsafe to "No pulses" or "Set position center", never "Last position". Then turn the radio off and check that the motors stop.

## Português

O TankMix adiciona **tank mix (mixagem diferencial)** ao módulo ExpressLRS interno do **RadioMaster T8L**, para dirigir um robô de dois motores com um stick só. O T8L não tem tela para mixer, e a interface web do ExpressLRS não tem tank mix. Por isso o mix roda dentro do módulo TX, antes de os canais serem enviados. O receptor continua com o ExpressLRS original.

O TankMix é só para o T8L. Rádios com EdgeTX ou OpenTX fazem esse mix no próprio rádio.

### O que ele faz

- **Confere o computador:** verifica Python, PlatformIO e Git, e explica como instalar o que faltar.
- **Baixa qualquer versão do ExpressLRS a partir da 3.5.0**, ou abre uma que você já tenha, e instala o mod nela.
- **Edita o mix:** canais, força da curva, zonas mortas e inversões. Uma prévia ao vivo usa a mesma conta do firmware, e configurações inválidas são barradas antes de chegar ao compilador.
- **Compila o firmware do T8L** com a sua binding phrase.
- **Grava no rádio por WiFi**.
- A interface é em **português e inglês**.

### Requisitos

| | Para quê |
|---|---|
| [Python](https://www.python.org/downloads/) 3.8+ | roda o TankMix (no Windows, marque "Add python.exe to PATH") |
| [PlatformIO Core](https://docs.platformio.org/en/latest/core/installation/methods/installer-script.html) | compila o firmware |
| [Git](https://git-scm.com/downloads) | baixa o ExpressLRS e os layouts de hardware |
| Internet | primeira compilação de cada versão e download de versões |

### Como usar

1. Extraia a release e abra a pasta `TankMix`.
2. Abra o TankMix:
   - **Windows:** clique duas vezes em `TankMix.bat`.
   - **macOS:** clique duas vezes em `TankMix.command`. Na primeira vez, clique com o botão direito e escolha **Abrir**.
   - **Linux:** rode `./tankmix.sh`.
3. O navegador abre. Resolva o que estiver em vermelho em **Verificação do sistema**.
4. Em **Pasta do ExpressLRS**, baixe uma versão ou digite o caminho de uma que você já tenha e clique em **Abrir**. Se o mod não estiver lá, clique em **Instalar tank mix**.
5. Configure o mix e clique em **Compilar firmware**.
6. No rádio, vá em Lua do ExpressLRS → **WiFi Connectivity** → **Enable WiFi**. Conecte o computador na rede WiFi do rádio e clique em **Gravar no rádio**.

Teste na bancada antes de usar o robô. Configure o failsafe do receptor como "No pulses" ou "Set position center", nunca "Last position". Depois desligue o rádio e confira que os motores param.
