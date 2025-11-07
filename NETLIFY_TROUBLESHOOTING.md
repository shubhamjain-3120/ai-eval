# Netlify 404 Error Troubleshooting

If you're getting a "Page not found" error when clicking "Evaluate All", follow these steps:

## 1. Check Function Deployment

In your Netlify dashboard:
- Go to **Functions** tab
- Verify that `evaluate` function appears in the list
- Check for any build errors in the **Deploys** tab

## 2. Verify Environment Variable

- Go to **Site settings** → **Environment variables**
- Ensure `OPENAI_API_KEY` is set
- Make sure there are no extra spaces or quotes
- **Redeploy** after adding/changing environment variables

## 3. Check Build Logs

- Go to **Deploys** tab
- Click on the latest deploy
- Check the build logs for:
  - Python function compilation errors
  - Missing dependencies
  - Import errors

## 4. Test Function Directly

Try accessing the function directly in your browser:
```
https://your-site-name.netlify.app/.netlify/functions/evaluate
```

You should get a response (even if it's an error about missing POST data).

## 5. Common Issues

### Issue: Function not found
**Solution**: 
- Ensure `netlify/functions/evaluate.py` exists
- Check that `netlify.toml` has `functions = "netlify/functions"`
- Redeploy the site

### Issue: Import errors
**Solution**:
- Check `netlify/functions/requirements.txt` includes all dependencies
- Ensure `openai` is listed in requirements.txt
- Check build logs for missing packages

### Issue: Timeout errors
**Solution**:
- Netlify Functions have a 10-second timeout on free tier
- Consider upgrading to paid plan (26-second timeout)
- Or optimize the evaluation process

### Issue: Redirect catching function
**Solution**:
- The redirect in `netlify.toml` should NOT affect `.netlify` paths
- Netlify handles function paths before applying redirects
- If still having issues, check the redirect configuration

## 6. Manual Function Test

You can test the function using curl:

```bash
curl -X POST https://your-site-name.netlify.app/.netlify/functions/evaluate \
  -H "Content-Type: application/json" \
  -d '{"sections": [{"rfp_text": "test", "rubric": "test"}]}'
```

## 7. Check Browser Console

Open browser DevTools (F12) and check:
- **Console** tab for JavaScript errors
- **Network** tab to see the actual request/response
- Look for the request to `/.netlify/functions/evaluate`

## 8. Verify Function Structure

The function should:
- Be in `netlify/functions/evaluate.py`
- Have a `handler(event, context)` function
- Return proper response format with `statusCode`, `headers`, and `body`

## Next Steps

If none of these work:
1. Check Netlify's function logs in the dashboard
2. Try redeploying from scratch
3. Verify your Netlify plan supports Python functions
4. Check if there are any function size limits being exceeded

