# Netlify Deployment Guide

This guide explains how to deploy the RFP Evaluation Tool to Netlify.

## Prerequisites

1. A Netlify account (sign up at https://netlify.com)
2. Your OpenAI API key
3. Git repository (optional, but recommended)

## Deployment Steps

### Option 1: Deploy via Netlify UI

1. **Prepare your repository**
   - Make sure all files are committed
   - Push to GitHub, GitLab, or Bitbucket

2. **Connect to Netlify**
   - Go to https://app.netlify.com
   - Click "Add new site" → "Import an existing project"
   - Connect your Git repository
   - Netlify will auto-detect the settings from `netlify.toml`

3. **Set Environment Variables**
   - Go to Site settings → Environment variables
   - Add `OPENAI_API_KEY` with your OpenAI API key value
   - Save

4. **Deploy**
   - Netlify will automatically build and deploy
   - Your site will be available at `https://your-site-name.netlify.app`

### Option 2: Deploy via Netlify CLI

1. **Install Netlify CLI**
   ```bash
   npm install -g netlify-cli
   ```

2. **Login to Netlify**
   ```bash
   netlify login
   ```

3. **Initialize and deploy**
   ```bash
   netlify init
   netlify deploy --prod
   ```

4. **Set environment variable**
   ```bash
   netlify env:set OPENAI_API_KEY your-api-key-here
   ```

## Project Structure

```
.
├── netlify/
│   ├── functions/
│   │   ├── evaluate.py          # Serverless function for evaluation
│   │   └── requirements.txt      # Python dependencies
├── public/
│   ├── index.html               # Main HTML file
│   └── static/
│       └── css/
│           └── style.css        # Stylesheet
├── netlify.toml                  # Netlify configuration
└── README_NETLIFY.md            # This file
```

## Important Notes

1. **Environment Variables**: Make sure to set `OPENAI_API_KEY` in Netlify's environment variables. Never commit your API key to the repository.

2. **Function Timeout**: Netlify Functions have a default timeout of 10 seconds for free tier, and up to 26 seconds for paid plans. If your evaluations take longer, consider:
   - Upgrading to a paid plan
   - Optimizing the evaluation process
   - Using a different deployment platform for longer-running operations

3. **API Endpoint**: The frontend calls `/.netlify/functions/evaluate` which is automatically handled by Netlify.

4. **Build Settings**: The `netlify.toml` file configures:
   - Publish directory: `public`
   - Functions directory: `netlify/functions`
   - SPA redirects for client-side routing

## Troubleshooting

### Function not found
- Ensure `netlify/functions/evaluate.py` exists
- Check that `netlify.toml` has the correct functions directory

### Environment variable not working
- Verify the variable is set in Netlify dashboard
- Redeploy after setting environment variables
- Check variable name matches exactly: `OPENAI_API_KEY`

### Build errors
- Check Netlify build logs
- Ensure all dependencies are listed in `netlify/functions/requirements.txt`
- Verify Python version compatibility

## Local Development

To test locally with Netlify Dev:

```bash
netlify dev
```

This will:
- Start a local development server
- Simulate Netlify Functions
- Load environment variables from `.env` file (create one if needed)

## Support

For issues specific to:
- **Netlify**: Check [Netlify documentation](https://docs.netlify.com)
- **OpenAI API**: Check [OpenAI documentation](https://platform.openai.com/docs)

