//+------------------------------------------------------------------+
//|                                               ExpertAdvisor.mq4  |
//+------------------------------------------------------------------+
#property strict

input double RiskPercent = 1.0;
input int    StopLossPips = 50;

int CalculateLotSize(double balance)
  {
   return(int)(balance * RiskPercent / 100.0);
  }

void OpenTrade(string symbol)
  {
   int lots = CalculateLotSize(AccountBalance());
   OrderSend(symbol, OP_BUY, lots, Ask, 3, Ask - StopLossPips * Point, 0, "EA", 0, 0, clrGreen);
  }

int OnInit()
  {
   OpenTrade(Symbol());
   return(INIT_SUCCEEDED);
  }
