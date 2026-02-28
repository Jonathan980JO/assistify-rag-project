# Complete GitHub Upload Guide for Beginners

## Part 1: Prepare Your Computer

### 1.1 Install Git
1. Open browser, go to: https://git-scm.com/download/win
2. Click "Click here to download"
3. Run the downloaded file
4. Click "Next" for all options (use defaults)
5. Click "Install"
6. Click "Finish"

### 1.2 Verify Git Installation
1. Press `Windows Key + R`
2. Type `cmd` and press Enter
3. Type: `git --version`
4. You should see something like: `git version 2.42.0.windows.1`

---

## Part 2: Create GitHub Account (if you don't have one)

### 2.1 Sign Up
1. Go to: https://github.com
2. Click "Sign up"
3. Enter your email
4. Create a password
5. Choose a username (example: `jonathan-aast`)
6. Verify you're human (puzzle)
7. Click "Create account"
8. Check your email and verify

### 2.2 Create Personal Access Token (Important!)
GitHub no longer accepts passwords for git operations. You need a token:

1. Log into GitHub
2. Click your profile picture (top right)
3. Click "Settings"
4. Scroll down, click "Developer settings" (bottom left)
5. Click "Personal access tokens" → "Tokens (classic)"
6. Click "Generate new token" → "Generate new token (classic)"
7. Name: `Assistify Project`
8. Expiration: Choose `No expiration` or `90 days`
9. Select scopes:
   - ✅ Check `repo` (all sub-items will auto-check)
   - ✅ Check `workflow`
10. Scroll down, click "Generate token" (bottom green button)
11. **IMPORTANT**: Copy the token immediately (starts with `ghp_`)
12. **Save it in Notepad** - you won't see it again!

Example token: `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

---

## Part 3: Create Repository on GitHub

### 3.1 Create New Repository
1. Log into GitHub
2. Click the `+` icon (top right corner)
3. Click "New repository"
4. Fill in:
   - **Repository name**: `assistify-rag-project`
   - **Description**: `Intelligent Help Desk with RAG & Voice Engine - Graduation Project`
   - **Visibility**: 
     - ✅ Public (anyone can see)
     - OR Private (only you and collaborators)
   - **Initialize**:
     - ❌ DO NOT check "Add README" (we already have one)
     - ❌ DO NOT add .gitignore (we already created it)
     - ❌ DO NOT choose license yet
5. Click "Create repository" (green button)

### 3.2 Copy Repository URL
You'll see a page with quick setup instructions. Look for:
```
…or create a new repository on the command line
```

Copy the HTTPS URL that looks like:
```
https://github.com/YOUR_USERNAME/assistify-rag-project.git
```

**Example:**
```
https://github.com/jonathan-aast/assistify-rag-project.git
```

**Write this URL down!** You'll need it soon.

---

## Part 4: Prepare Your Project Files

### 4.1 Open Command Prompt in Project Folder
1. Open File Explorer
2. Navigate to: `C:\Users\Jonathan\Desktop\AAST\Graduation Project`
3. Click in the address bar at the top (where it shows the path)
4. Type `cmd` and press Enter
   - A black Command Prompt window will open **in your project folder**

### 4.2 Verify You're in Correct Folder
In the Command Prompt, type:
```bash
dir
```

You should see folders like:
- backend
- frontend
- Login_system
- scripts
- docs

If you see these, you're in the right place! ✅

---

## Part 5: Upload to GitHub (Step by Step)

Copy and paste these commands **one at a time**. Wait for each to finish before running the next.

### 5.1 Initialize Git Repository
```bash
git init
```

**Expected output:**
```
Initialized empty Git repository in C:/Users/Jonathan/Desktop/AAST/Graduation Project/.git/
```

### 5.2 Add All Files
```bash
git add .
```

**Expected output:** (Nothing displayed = success)

**What this does:** Prepares all files for upload (the `.gitignore` file automatically excludes things like `__pycache__`, `.db`, model files)

### 5.3 Create First Commit
```bash
git commit -m "Initial commit - Assistify RAG project"
```

**Expected output:**
```
[main (root-commit) abc1234] Initial commit - Assistify RAG project
 XX files changed, XXXX insertions(+)
 create mode 100644 README.md
 create mode 100644 config.py
 ...
```

### 5.4 Rename Branch to 'main'
```bash
git branch -M main
```

**Expected output:** (Nothing displayed = success)

### 5.5 Connect to Your GitHub Repository
**Replace `YOUR_USERNAME` with your actual GitHub username:**

```bash
git remote add origin https://github.com/YOUR_USERNAME/assistify-rag-project.git
```

**Example (if your username is `jonathan-aast`):**
```bash
git remote add origin https://github.com/jonathan-aast/assistify-rag-project.git
```

**Expected output:** (Nothing displayed = success)

### 5.6 Push to GitHub
```bash
git push -u origin main
```

**You'll be prompted for credentials:**

```
Username for 'https://github.com':
```
Type your GitHub **username** and press Enter

```
Password for 'https://YOUR_USERNAME@github.com':
```
**PASTE YOUR PERSONAL ACCESS TOKEN** (the one starting with `ghp_`)
- Right-click to paste in Command Prompt
- You won't see the token as you paste (this is normal)
- Press Enter

**Expected output (success):**
```
Enumerating objects: 100, done.
Counting objects: 100% (100/100), done.
Delta compression using up to 8 threads
Compressing objects: 100% (80/80), done.
Writing objects: 100% (100/100), 50.00 KiB | 5.00 MiB/s, done.
Total 100 (delta 20), reused 0 (delta 0), pack-reused 0
To https://github.com/YOUR_USERNAME/assistify-rag-project.git
 * [new branch]      main -> main
Branch 'main' set up to track remote branch 'main' from 'origin'.
```

🎉 **Success! Your project is now on GitHub!**

---

## Part 6: Verify Upload

### 6.1 Check GitHub Website
1. Go to: `https://github.com/YOUR_USERNAME/assistify-rag-project`
2. You should see:
   - Your README.md displayed
   - All folders: backend, frontend, Login_system, scripts, docs
   - Files like config.py, requirements.txt
   - Total file count displayed

### 6.2 What Files Were Uploaded?
✅ **Uploaded:**
- All .py files (Python code)
- README.md, requirements.txt, .gitignore
- config.py
- Documentation files
- HTML/CSS/JS files

❌ **NOT Uploaded (because of .gitignore):**
- `__pycache__/` folders
- `*.db` database files
- `backend/Models/*.gguf` (model files - too large!)
- `chroma_db/` folders
- `.env` file (contains secrets)

This is **correct and expected!** 👍

---

## Part 7: Add Collaborator (Your Friend)

### 7.1 Invite Your Friend
1. Go to your repository on GitHub
2. Click "Settings" tab
3. Click "Collaborators" (left sidebar)
4. Click "Add people"
5. Enter your friend's GitHub username or email
6. Click "Add [username] to this repository"
7. Your friend will receive an email invitation

### 7.2 Your Friend Accepts
1. Friend checks email
2. Clicks "View invitation"
3. Clicks "Accept invitation"
4. Now friend has access!

---

## Part 8: Your Friend Downloads the Project

### 8.1 Send Your Friend This Information
Send them:
1. **Repository URL**: `https://github.com/YOUR_USERNAME/assistify-rag-project`
2. **Model download links** (these files are too large for GitHub):
   - Qwen model: https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF
   - Files needed: Both `qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf` AND `qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf`
3. **Setup file**: `SETUP_REQUIREMENTS.md` (already in repository)

### 8.2 Your Friend's Steps

#### Step 1: Install Git
(Same as Part 1.1 above)

#### Step 2: Open Command Prompt
1. Press `Windows Key + R`
2. Type `cmd`, press Enter
3. Navigate to Desktop:
```bash
cd Desktop
mkdir AAST
cd AAST
```

#### Step 3: Clone Repository
```bash
git clone https://github.com/YOUR_USERNAME/assistify-rag-project.git
```

**If repository is private**, will be prompted:
- Username: Friend's GitHub username
- Password: Friend's Personal Access Token

**Expected output:**
```
Cloning into 'assistify-rag-project'...
remote: Enumerating objects: 100, done.
remote: Counting objects: 100% (100/100), done.
remote: Compressing objects: 100% (80/80), done.
Receiving objects: 100% (100/100), 50.00 KiB | 5.00 MiB/s, done.
Resolving deltas: 100% (20/20), done.
```

#### Step 4: Enter Project Folder
```bash
cd assistify-rag-project
```

#### Step 5: Download Model Files
1. Create folder: `mkdir backend\Models\Qwen2.5-7B-LLM`
2. Download both GGUF files from HuggingFace
3. Place in `backend\Models\Qwen2.5-7B-LLM\`

#### Step 6: Follow Setup Requirements
```bash
# Follow SETUP_REQUIREMENTS.md step by step
conda create -n grad python=3.11 -y
conda activate grad
pip install -r requirements.txt
# ... (continue with remaining steps)
```

---

## Part 9: Making Changes Later

### 9.1 You Make Changes to Code

After editing files on your computer:

```bash
# 1. Check what changed
git status

# 2. Add all changed files
git add .

# 3. Commit with descriptive message
git commit -m "Fixed voice recording silence detection bug"

# 4. Push to GitHub
git push
```

**Credentials:** May ask for username and token again

### 9.2 Your Friend Gets Your Changes

Your friend opens Command Prompt in project folder and types:
```bash
git pull
```

This downloads your latest changes! ✅

### 9.3 Your Friend Makes Changes

Friend follows same steps (9.1 above):
```bash
git add .
git commit -m "Added new knowledge base documents"
git push
```

### 9.4 You Get Friend's Changes
```bash
git pull
```

---

## Part 10: Common Commands Summary

```bash
# Check status (what changed?)
git status

# Add all changes
git add .

# Commit changes
git commit -m "Description of what you changed"

# Upload to GitHub
git push

# Download latest from GitHub
git pull

# See commit history
git log

# See what branch you're on
git branch
```

---

## Part 11: Common Problems & Solutions

### Problem 1: "Permission denied (publickey)" or "Authentication failed"
**Cause**: Using wrong credentials

**Solution**: 
- Username: Your GitHub username (not email)
- Password: Personal Access Token (starts with `ghp_`), NOT your GitHub account password

### Problem 2: "Repository not found"
**Cause**: Wrong URL or repository is private and you're not a collaborator

**Solution**: 
- Double-check URL is correct
- Make sure you replaced `YOUR_USERNAME` with actual username
- If private repo, make sure you're added as collaborator

### Problem 3: "Failed to push" or "Updates were rejected"
**Cause**: GitHub has changes you don't have locally

**Solution**: 
```bash
git pull origin main
git push origin main
```

### Problem 4: "Large file error" - File exceeds 100MB
**Cause**: Trying to upload model files (too large for GitHub)

**Solution**: 
- Model files should already be in `.gitignore`
- If you see this error, verify `.gitignore` exists
- Remove large file from staging:
```bash
git rm --cached path/to/large/file
git commit -m "Removed large file"
```

### Problem 5: "Merge conflict"
**Cause**: You and friend changed the same line in same file

**Solution**: 
```bash
git pull
# Edit conflicted files (look for <<<<<<< markers)
# Choose which version to keep
git add .
git commit -m "Resolved merge conflict"
git push
```

### Problem 6: Forgot Personal Access Token
**Solution**: 
- Create a new token (Part 2.2)
- Store it safely this time (Notepad, password manager)

---

## Part 12: Model Files - Special Handling

### Why Model Files Aren't in GitHub
- Model files are 4-5GB (GitHub limit: 100MB per file)
- `.gitignore` excludes them automatically
- Must be shared separately

### Option 1: Google Drive (Recommended)
1. Upload model files to Google Drive
2. Right-click → "Get link" → "Anyone with link can view"
3. Send link to your friend

### Option 2: Direct Download
1. Friend downloads from HuggingFace (original source)
2. Slower but most reliable

### Option 3: Git LFS (Advanced)
If you want models in GitHub:
```bash
# Install Git LFS
git lfs install

# Track large files
git lfs track "*.gguf"

# Add .gitattributes
git add .gitattributes

# Now can add model files
git add backend/Models/*.gguf
git commit -m "Add model files via LFS"
git push
```

**Note:** Git LFS has storage limits on free accounts

---

## Part 13: Quick Reference Card

### First Time Upload
```bash
cd "C:\path\to\project"
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/USERNAME/repo.git
git push -u origin main
```

### Regular Updates
```bash
git add .
git commit -m "Description"
git push
```

### Get Updates
```bash
git pull
```

### Check Status
```bash
git status
git log
```

---

## Part 14: Checklist Before Pushing

- [ ] `.gitignore` file exists in project root
- [ ] `requirements.txt` file exists
- [ ] No `.env` file in folder (or it's in .gitignore)
- [ ] No large model files (or they're in .gitignore)
- [ ] All important code saved
- [ ] Tested code works locally
- [ ] README.md exists and describes project

---

## Part 15: What Your Repository Should Look Like

After successful push, GitHub should show:

```
assistify-rag-project/
├── 📁 backend/
│   ├── main_llm_server.py
│   ├── assistify_rag_server.py
│   ├── knowledge_base.py
│   ├── database.py
│   └── ... (other .py files)
├── 📁 Login_system/
│   └── login_server.py
├── 📁 frontend/
│   └── index.html
├── 📁 scripts/
│   └── project_start_server.py
├── 📁 docs/
│   └── (documentation files)
├── 📄 .gitignore
├── 📄 README.md
├── 📄 requirements.txt
├── 📄 config.py
└── 📄 SETUP_REQUIREMENTS.md
```

**NOT visible (excluded by .gitignore):**
- ❌ __pycache__ folders
- ❌ .db files
- ❌ backend/Models/ (model files)
- ❌ chroma_db/
- ❌ .env

---

## Summary

1. **Install Git** → Verify with `git --version`
2. **Create GitHub account** → Generate Personal Access Token → Save it!
3. **Create repository** on GitHub → Copy URL
4. **Open CMD** in project folder → `cd "path\to\project"`
5. **Run commands:**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin URL
   git push -u origin main
   ```
6. **Enter credentials:** Username + Token
7. **Verify** on GitHub website
8. **Share link** with friend + model download links

**You're done!** 🎉

Your project is now on GitHub and your friend can download it!
