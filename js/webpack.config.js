var version = require('./package.json').version;

const babelSettings = {
  plugins: [
    'add-module-exports',
    'transform-regenerator',
    'transform-decorators-legacy'
  ],
  presets: [ 'es2015', 'react', 'stage-1' ]
};


module.exports = [{
  entry: './src/index.js',
  output: {
    filename: 'index.js',
    path: '../timbr/static',
    libraryTarget: 'amd'
  },
  module: {
    preLoaders: [{
      test: /\.js$/,
      loader: 'source-map-loader'
    }],
    loaders : [{
      test: /\.js?$/,
      exclude: /(node_modules|bower_components)/,
      loaders: [`babel?${JSON.stringify( babelSettings )}`]
    }, { 
      test: /\.css$/, 
      loader: "style-loader!css-loader" 
    }, {
      test: /\.less$/, 
      loader: "style!css!less?sourceMap"
    }]
  },
  devtool: 'cheap-module-source-map'
}];
