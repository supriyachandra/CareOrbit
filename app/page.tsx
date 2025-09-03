"use client"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Hospital, Users, UserCheck, Calendar } from "lucide-react"
import Link from "next/link"

export default function HomePage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="container mx-auto px-4 py-16">
        {/* Header */}
        <div className="text-center mb-16">
          <div className="flex justify-center items-center mb-6">
            <Hospital className="h-16 w-16 text-blue-600 mr-4" />
            <h1 className="text-5xl font-bold text-gray-900">CareOrbit</h1>
          </div>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto">
            Comprehensive Hospital Management System for streamlined patient care and administrative efficiency
          </p>
        </div>

        {/* Login Cards */}
        <div className="grid md:grid-cols-2 gap-8 max-w-4xl mx-auto mb-16">
          <Card className="hover:shadow-lg transition-shadow duration-300">
            <CardHeader className="text-center">
              <div className="flex justify-center mb-4">
                <UserCheck className="h-12 w-12 text-blue-600" />
              </div>
              <CardTitle className="text-2xl">Admin Portal</CardTitle>
              <CardDescription>Manage patients, assign doctors, and oversee hospital operations</CardDescription>
            </CardHeader>
            <CardContent className="text-center">
              <Link href="/admin/login">
                <Button className="w-full bg-blue-600 hover:bg-blue-700">Admin Login</Button>
              </Link>
            </CardContent>
          </Card>

          <Card className="hover:shadow-lg transition-shadow duration-300">
            <CardHeader className="text-center">
              <div className="flex justify-center mb-4">
                <Users className="h-12 w-12 text-green-600" />
              </div>
              <CardTitle className="text-2xl">Doctor Portal</CardTitle>
              <CardDescription>Access patient records, manage appointments, and provide care</CardDescription>
            </CardHeader>
            <CardContent className="text-center">
              <Link href="/doctor/login">
                <Button className="w-full bg-green-600 hover:bg-green-700">Doctor Login</Button>
              </Link>
            </CardContent>
          </Card>
        </div>

        {/* Features */}
        <div className="grid md:grid-cols-3 gap-6 max-w-6xl mx-auto">
          <div className="text-center p-6">
            <Calendar className="h-10 w-10 text-blue-600 mx-auto mb-4" />
            <h3 className="text-lg font-semibold mb-2">Appointment Management</h3>
            <p className="text-gray-600">Efficient scheduling and patient assignment system</p>
          </div>

          <div className="text-center p-6">
            <Hospital className="h-10 w-10 text-blue-600 mx-auto mb-4" />
            <h3 className="text-lg font-semibold mb-2">Patient Records</h3>
            <p className="text-gray-600">Comprehensive medical history and treatment tracking</p>
          </div>

          <div className="text-center p-6">
            <Users className="h-10 w-10 text-blue-600 mx-auto mb-4" />
            <h3 className="text-lg font-semibold mb-2">Staff Management</h3>
            <p className="text-gray-600">Doctor scheduling and department coordination</p>
          </div>
        </div>

        {/* Footer */}
        <div className="text-center mt-16 text-gray-500">
          <p>&copy; 2024 CareOrbit Hospital Management System. All rights reserved.</p>
        </div>
      </div>
    </div>
  )
}
