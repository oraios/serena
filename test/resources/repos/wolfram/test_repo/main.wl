Get["lib/helper.wl"]

calculateSum[a_, b_] := a + b

processData[data_List] := Module[{result},
    result = Total[data];
    formatResult[result]
]

main[] := Module[{result, greeting},
    result = calculateSum[5, 3];
    greeting = sayHello["World"];
    Print[greeting];
    Print[result]
]

main[]
