package com.example.testapp;

import android.util.Log;

public class JavaUtils {
    private static final String TAG = "JavaUtils";
    
    public static void logMessage(String message) {
        Log.d(TAG, message);
        System.out.println("JavaUtils: " + message);
    }
    
    public static String formatUserInfo(UserModel user) {
        return String.format("User: %s (Age: %d)", user.getName(), user.getAge());
    }
    
    public static boolean isAdult(UserModel user) {
        return user.getAge() >= 18;
    }
}