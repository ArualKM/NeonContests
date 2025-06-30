# Multi-Platform Music Contest Discord Bot

A powerful and flexible Discord bot designed to run music submission contests on your server. It supports multiple music creation and streaming platforms, provides a robust system for anonymous voting, and includes comprehensive admin controls for seamless contest management.

## 🌟 Features

  - **Multi-Platform Support:** Accepts submissions from Suno, Udio, Riffusion, YouTube, and SoundCloud.
  - **Customizable Contests:** Admins can create contests and optionally restrict submissions to specific platforms.
  - **Anonymous Voting:** Submissions are posted publicly without revealing the submitter's identity to ensure fair voting.
  - **Private Admin Channel:** A dedicated channel for admins to see full submission details, including who submitted the track.
  - **Automated Metadata Fetching:** The bot automatically fetches the song title, author, and cover art from the provided URL.
  - **Secure and Robust:** Features built-in confirmation dialogues for critical actions like deleting contests or submissions.
  - **Full Management Control:** Admins can create, edit, and delete contests. Users (and admins) can delete submissions.

## 🎵 Supported Platforms

  - Suno
  - Udio
  - Riffusion
  - YouTube
  - SoundCloud

## 🤖 Commands

The bot uses Discord's slash commands for all interactions.

### Admin Commands

These commands require the user to have "Administrator" permissions on the server.

#### `/contest create`

Creates a new music contest.

  - **`contest_id`**: A unique ID for the contest (e.g., `weekly-5`, `summer2025`).
  - **`public_channel`**: The channel where anonymous submissions will be posted for voting.
  - **`review_channel`**: The private channel where admins can see full submission details.
  - **`allowed_platforms`** `(Optional)`: A comma-separated list of platforms to accept (e.g., `suno,youtube`). If left blank, all platforms are allowed.

#### `/contest edit`

Edits the channels for an existing contest.

  - **`contest_id`**: The ID of the contest to edit.
  - **`public_channel`** `(Optional)`: The new public channel for voting.
  - **`review_channel`** `(Optional)`: The new private channel for admin review.

#### `/contest delete`

Deletes a contest and ALL associated submissions. This action is irreversible and requires confirmation.

  - **`contest_id`**: The ID of the contest to delete.

### User Commands

#### `/submit`

Submits a track to a contest. This command can be used in any channel, but the command and its response will only be visible to you (ephemeral).

  - **`contest_id`**: The ID of the contest you are entering.
  - **`song_name`**: The name of your track.
  - **`url`**: The full URL to your song on a supported platform.

#### `/submission delete`

Deletes one of your submissions. This can also be used by an administrator to delete any submission.

  - **`submission_id`**: The unique ID of the submission to delete. This ID is found in the footer of every submission post.

## 🛠️ Installation & Setup

Follow these steps to get the bot running on your own server.

### Prerequisites

  - [Python 3.8+](https://www.python.org/downloads/)
  - A Discord account with admin privileges on a server.

### 1\. Create a Discord Bot Application

1.  Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2.  Create a **New Application**.
3.  Go to the **Bot** tab and click **Add Bot**.
4.  **Copy the Bot Token.** You will need this for the `.env` file.
5.  Enable **Privileged Gateway Intents**:
      - `SERVER MEMBERS INTENT`
      - `MESSAGE CONTENT INTENT`
6.  Go to the **OAuth2 \> URL Generator** tab.
      - Select scopes: `bot` and `applications.commands`.
      - Select Bot Permissions: `Send Messages`, `Manage Messages`, `Embed Links`, and `Read Message History`.
7.  Copy the generated URL, paste it into your browser, and invite the bot to your server.

### 2\. Set Up the Project

1.  Clone this repository or download the source files into a folder.
2.  Install the required Python libraries:
    ```bash
    pip install py-cord python-dotenv requests beautifulsoup4
    ```
3.  Create a file named `.env` in the main project folder. Add your bot token to it like so:
    ```
    DISCORD_TOKEN=YOUR_BOT_TOKEN_HERE
    ```
4.  Initialize the database by running the `database.py` script once:
    ```bash
    python database.py
    ```
    This will create a `suno_contests.db` file in your project folder.

### 3\. Run the Bot

Start the bot by running the `main.py` script:

```bash
python main.py
```

If everything is configured correctly, you will see a confirmation message in your terminal, and the bot will appear as "online" in your Discord server.

## 🚀 Usage Guide

1.  **Create Channels:** In your Discord server, create a public channel for voting (e.g., `#music-contest`) and a private channel for admins (e.g., `#admin-review`).
2.  **Create a Contest:** Use the `/contest create` command to set up your first contest, linking it to the channels you just created.
3.  **Announce the Contest:** Let your server members know the `contest_id` and that they can submit tracks using the `/submit` command.
4.  **Manage and Vote:** As submissions come in, they will be posted anonymously in the public channel where users can vote by reacting with the ✅ emoji. Admins can monitor all submission details in the private review channel.
