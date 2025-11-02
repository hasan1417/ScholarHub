import http from 'node:http'

const port = Number.parseInt(process.env.PORT ?? '3001', 10)

const request = http.get({ host: '127.0.0.1', port, path: '/', timeout: 3000 }, (res) => {
  if (res.statusCode === 200) {
    res.resume()
    process.exit(0)
  } else {
    res.resume()
    console.error(`Unexpected status code: ${res.statusCode}`)
    process.exit(1)
  }
})

request.on('error', (error) => {
  console.error(error)
  process.exit(1)
})
