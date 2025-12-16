## Demo

The application includes a lightweight Streamlit UI that allows users to adjust
financing and operating assumptions and instantly see the impact on:

- Monthly cash flow
- Cash-on-cash return
- Cap rate

![Streamlit UI Demo](UI_Screenshot_(1))
![Streamlit UI Demo](UI_Screenshot_(2))

## Dashboard

### QuickCheck
![QuickCheck](Quickcheck Image)

### Saved Deals
![Saved Deals](Saved Deals Image)

### Compare Deals
![Compare Deals](Compare Deals Image)

## Run locally

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py

