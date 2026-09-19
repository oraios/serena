//+------------------------------------------------------------------+
//|                                              TradingClass.mq5    |
//+------------------------------------------------------------------+
#include "IncludeUtils.mqh"

class TradingClass
  {
private:
   double            m_balance_factor;

public:
                     TradingClass(void) : m_balance_factor(1.0) {}
                    ~TradingClass(void) {}
   void              Execute(void)
     {
      double lots = NormalizeLot(0.5);
      m_balance_factor = lots;
      Print("executing ", m_balance_factor);
     }
   double            BalanceFactor(void) const { return m_balance_factor; }
  };
