# Deploying to Render

This guide explains how to deploy the RFP Evaluation Tool to Render.

## Prerequisites

1. A Render account (sign up at https://render.com - free tier available)
2. Your OpenAI API key
3. GitHub repository (already set up)

## Deployment Steps

### Option 1: Using render.yaml (Recommended)

1. **Push your code to GitHub** (already done)

2. **Go to Render Dashboard**
   - Visit https://dashboard.render.com
   - Sign up or log in

3. **Create New Web Service**
   - Click "New +" → "Web Service"
   - Connect your GitHub account if not already connected
   - Select your repository: `ai-eval`

4. **Configure Service**
   - Render will auto-detect settings from `render.yaml`
   - Service name: `rfp-evaluation-tool` (or your choice)
   - Environment: Python 3
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`

5. **Set Environment Variable**
   - In the Environment section, add:
     - Key: `OPENAI_API_KEY`
     - Value: Your OpenAI API key
   - Click "Save Changes"

6. **Deploy**
   - Click "Create Web Service"
   - Render will build and deploy your app
   - Your app will be available at `https://rfp-evaluation-tool.onrender.com` (or your custom domain)

### Option 2: Manual Configuration

If you prefer to configure manually:

1. **Create New Web Service** in Render
2. **Connect Repository**: Select `ai-eval` repository
3. **Settings**:
   - **Name**: rfp-evaluation-tool
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Plan**: Free
4. **Environment Variables**:
   - Add `OPENAI_API_KEY` with your API key value
5. **Deploy**

## Important Notes

1. **Free Tier**: 
   - Services spin down after 15 minutes of inactivity
   - First request after spin-down may take 30-60 seconds
   - Consider upgrading to paid plan for always-on service

2. **Environment Variables**:
   - Never commit your API key to the repository
   - Always set it in Render's environment variables section

3. **Port Configuration**:
   - The app automatically uses the PORT environment variable provided by Render
   - No manual port configuration needed

4. **Static Files**:
   - Flask serves static files from the `static/` directory automatically
   - No additional configuration needed

5. **Templates**:
   - Flask serves HTML from the `templates/` directory automatically
   - The frontend already uses the correct endpoint (`/evaluate`)

## Testing

After deployment:
1. Visit your Render URL
2. Test adding sections
3. Test the "Evaluate All Sections" functionality
4. Check logs in Render dashboard if issues occur

## Monitoring

- **Logs**: View real-time logs in Render dashboard
- **Metrics**: Monitor CPU, memory, and request metrics
- **Alerts**: Set up alerts for errors or downtime

## Troubleshooting

### Service won't start
- Check build logs for dependency errors
- Verify `requirements.txt` is correct
- Ensure `Procfile` exists and is correct

### 500 errors
- Check application logs in Render dashboard
- Verify `OPENAI_API_KEY` is set correctly
- Check OpenAI API quota/limits

### Slow first request
- Normal on free tier (service spins down after inactivity)
- Consider upgrading to paid plan for always-on service

## Support

For issues:
- **Render**: Check [Render documentation](https://render.com/docs)
- **Application**: Check application logs in Render dashboard

