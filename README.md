# 🚀 CryptoVision Dashboard

## 💡 About the Project

**CryptoVision Dashboard** is an interactive web application developed in Python that allows real-time visualization of the main cryptocurrencies in the market. This project demonstrates the implementation of a complete dashboard using the CoinMarketCap API, featuring dynamic visualizations and financial data analysis.

### 🔍 Key Features

- **Real-Time Monitoring**: Track prices and fluctuations of top cryptocurrencies.
- **Advanced Data Visualization**: Interactive charts for market cap and trend analysis.
- **Responsive Interface**: Modern design adaptable to different devices.
- **Data Export**: Export data in CSV format.
- **Instant Updates**: Button for on-demand data refresh.

## 🛠️ Technologies Used

<div align="center">
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white" alt="Streamlit">
  <img src="https://img.shields.io/badge/Plotly-3F4F75?style=for-the-badge&logo=plotly&logoColor=white" alt="Plotly">
  <img src="https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white" alt="Pandas">
  <img src="https://img.shields.io/badge/API-REST-009688?style=for-the-badge&logo=api&logoColor=white" alt="REST API">
</div>

- **Backend**: Python 3.11 for data processing and business logic.
- **Frontend**: Streamlit for interactive and responsive web interface.
- **Visualization**: Plotly for dynamic and interactive charts.
- **Data**: Pandas for data manipulation and analysis.
- **API**: Integration with CoinMarketCap API via Requests.
- **Styling**: Custom CSS for a professional theme.

## ⚙️ Project Architecture

The project follows a modular and well-organized architecture:

```
crypto_dashboard/
│
├── app.py                # Main application and Streamlit interface
├── api.py                # CoinMarketCap API integration module
├── utils.py              # Utility functions for data processing
├── requirements.txt      # Project dependencies
└── screenshots/          # Dashboard screenshots
```

## 📊 Implemented Features

- **Main Dashboard**: Overview of the cryptocurrency market.
- **Interactive Table**: List of top cryptocurrencies with detailed data.
- **Real-Time Metrics**: Total market cap, average change, and volume.
- **Market Cap Charts**: Comparative visualization among major coins.
- **Variation Charts**: Performance analysis over 24-hour periods.
- **Data Export**: Option to save data in CSV format.
- **Customization**: Interface with a professional white and purple theme.

## 🚀 How to Run the Project

### Prerequisites

- Python 3.6 or higher
- Pip (Python package manager)

### Installation

1. Clone this repository:
```bash
git clone https://github.com/your-username/cryptovision-dashboard.git
cd cryptovision-dashboard
```

2. Create and activate a virtual environment:
```bash
python -m venv venv

# On Windows
venv\Scripts\activate

# On Linux/Mac
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the application:
```bash
streamlit run app.py
```

5. Access the dashboard in your browser (usually at http://localhost:8501)

## 🧠 Learnings and Challenges

During the development of this project, I enhanced several technical skills:

- **REST API Consumption**: Implementing authenticated requests and handling responses.
- **Financial Data Handling**: Processing and formatting market data.
- **Interactive Visualization**: Creating dynamic charts for data analysis.
- **Interface Design**: Developing an intuitive and responsive UI/UX.
- **Code Modularization**: Structuring the project with reusable components.

## 🔮 Future Improvements

- Implementing user authentication.
- Adding price history with time series.
- Creating custom price alerts.
- Integrating multiple data sources.
- Implementing predictive analytics with machine learning.

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributions

Contributions are welcome! Feel free to open issues or submit pull requests with improvements.

## 📬 Contact

- LinkedIn: [Caio Venancio](https://www.linkedin.com/in/caio-venancio/)
- GitHub: [@CaioVenxncio](https://github.com/CaioVenxncio)
- Email: caiovenanciocommercial@gmail.com

---

<div align="center">
  <p>Developed with ❤️ and ☕</p>
</div>


