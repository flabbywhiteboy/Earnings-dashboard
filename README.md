# Susan's Earnings Dashboard

This version is ready for Railway deployment.

## Files
- `app.py` - the Flask app
- `holdings.json` - your companies
- `requirements.txt` - Python packages
- `Procfile` - tells Railway how to start the app

## Deploy to Railway
1. Create a new GitHub repository.
2. Upload these files to the repo.
3. In Railway, create a new project and choose **Deploy from GitHub repo**.
4. Select your repo.
5. In Railway project settings, add this environment variable:
   - `ALPHAVANTAGE_API_KEY` = your Alpha Vantage key
6. Deploy.
7. Open the Railway URL on your iPhone in Safari.
8. Tap Share -> Add to Home Screen.

## Edit later
- Add/remove companies in `holdings.json`
- Add a Chemist Warehouse target price later by changing `price_target` for `SIG.AX`
- Add direct webcast URLs by filling in `webcast_url`